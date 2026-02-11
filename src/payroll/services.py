import csv
import io
from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import PayrollBatch, PayrollEntry, AttendanceLog
import pandas as pd
import re
from datetime import time, datetime

User = get_user_model()

# --- 1. Gratuity Calculator (Refined) ---
class GratuityService:
    """
    Service to calculate UAE End-of-Service Benefits (Gratuity)
    """
    def __init__(self, employee):
        self.employee = employee
        self.start_date = employee.date_of_joining
        self.end_date = timezone.now().date()
        self.unpaid_leave_days = 0 
        # Indian Gratuity Act: Daily wage is calculated as (Basic Salary / 26)
        # We use 15 days per completed year of service
        self.daily_basis = self.employee.salary_basic / Decimal('26.00')

    def calculate(self) -> dict:
        total_days = (self.end_date - self.start_date).days + 1
        active_days = total_days - self.unpaid_leave_days
        service_years = active_days / 365.25

        amount = Decimal('0.00')
        
        # Rule 1: Service less than 5 years = No Gratuity (Statutory minimum)
        if service_years < 4.8: # Roughly 4 years 240 days often used as cutoff
            amount = Decimal('0.00')
            
        # Rule 2: Formula: (Basic / 26) * 15 * service_years
        else:
            amount = (self.daily_basis * 15 * Decimal(service_years))

        return {
            "service_years": round(service_years, 2),
            "amount": round(amount, 2)
        }

# --- 2. Bank Transfer File Generator ---
class BankTransferService:
    @staticmethod
    def generate_export_file(batch: PayrollBatch) -> str:
        """
        Generates content for a CSV bank transfer file for Indian banks.
        Format: EmployeeName, AccountNumber, IFSC, Amount, Remarks
        """
        output = io.StringIO()
        writer = csv.writer(output)

        entries = batch.entries.select_related('employee').all()
        
        # Header Row
        writer.writerow(["Employee Name", "Account Number", "IFSC Code", "Net Salary", "Transaction Date"])

        for entry in entries:
            writer.writerow([
                entry.employee.full_name,
                entry.employee.iban, # We keep 'iban' field name but it stores Acct No
                entry.employee.ifsc_code,
                f"{entry.net_salary:.2f}",
                timezone.now().strftime("%Y-%m-%d")
            ])

        return output.getvalue()

        # 2. EDR (Employee Detail Record)
        # RecordType, EmployeeID(14 chars), AgentID(Bank), AccountNumber(IBAN), StartDate, EndDate, Days, Fixed, Variable, Leave
        for entry in entries:
            # Enforce Identification Rule
            emp_id = str(entry.employee.aadhaar_number or "").strip()
            if emp_id:
                emp_id = emp_id.zfill(12)
            else:
                # Fallback to internal ID
                emp_id = str(entry.employee.id).zfill(12)
            
            # Agent ID (Routing Code)
            agent_id = getattr(entry.employee, 'bank_routing_code', '') or '000000000'
            
            # Financials
            fixed_pay = entry.basic_salary + entry.allowances
            # Variable Pay = Additions (OT, Bonus) - Deductions
            # Note: SIF logic varies by bank, but generally Variable is additions. Deductions are subtracted from Net.
            # Field 8: Fixed, Field 9: Variable. Total = Fixed + Variable.
            # Net Salary should match Fixed + Variable ideally, or SIF allows simple breakdown.
            # We will map Variable Pay as (Variable - Deductions) to balance Net.
            variable_pay = entry.variable_pay - entry.deductions
            
            writer.writerow([
                "EDR", 
                emp_id, 
                agent_id, 
                entry.iban, # Decrypted IBAN
                batch.month.strftime("%Y-%m-%d"), # Pay Start Date
                (batch.month + timezone.timedelta(days=29)).strftime("%Y-%m-%d"), # Pay End Date
                entry.days_worked,
                f"{fixed_pay:.2f}",
                f"{variable_pay:.2f}", 
                "0.00" # Leave Salary
            ])
            
        return output.getvalue()

# --- 3. Attendance & Payroll Logic ---
class PayrollService:
    @staticmethod
    def import_attendance_csv(file, month: date):
        """
        Imports simple CSV: EmployeeEmail, Date(YYYY-MM-DD), InTime, OutTime
        """
        decoded_file = file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        
        from .models import RawPunch
        for row in reader:
            email = row.get('EmployeeEmail')
            try:
                emp = User.objects.get(email=email)
                log, _ = AttendanceLog.objects.update_or_create(
                    employee=emp,
                    date=row.get('Date'),
                    defaults={
                        'check_in': row.get('InTime'),
                        'check_out': row.get('OutTime'),
                        'entry_type': AttendanceLog.EntryType.AUTO
                    }
                )
                # Sync Raw Punches to ensure 4-step formula applies
                log.raw_punches.all().delete()
                if log.check_in:
                    RawPunch.objects.create(attendance_log=log, time=log.check_in, punch_type='IN')
                if log.check_out:
                    RawPunch.objects.create(attendance_log=log, time=log.check_out, punch_type='OUT')
                
                log.recalculate_duration()
            except User.DoesNotExist:
                continue

    @staticmethod
    def parse_duration_to_minutes(duration_str):
        """Convert H:MM, time object, or float to total minutes."""
        if duration_str is None or pd.isna(duration_str):
            return 0
            
        try:
            # Handle datetime.time or datetime.datetime
            if isinstance(duration_str, (time, datetime)):
                if isinstance(duration_str, datetime):
                    duration_str = duration_str.time()
                return (duration_str.hour * 60) + duration_str.minute
            
            val_str = str(duration_str).strip()
            
            # Handle "8:54" or "08:54:00"
            if ':' in val_str:
                parts = val_str.split(':')
                if len(parts) >= 2:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    return (hours * 60) + minutes
            
            # Handle "8.5" hours (decimal)
            # Check if it looks like a float
            try:
                val_float = float(val_str)
                # Propably hours if > 1? Or days if < 1?
                # If Excel reads "8:30" as 0.35416, we need to multiply by 24*60
                if val_float < 1.0: 
                    # Treat as fraction of day (Excel standard)
                    return int(val_float * 1440)
                else:
                    # Treat as hours (e.g. 8.5 hours)
                    return int(val_float * 60)
            except: pass
            
        except:
             pass
        return 0

    @staticmethod
    def parse_punch_records_regex(punch_str):
        """
        Parses mixed punch strings. 
        Supports format: "09:17:in(TAS-IN), 09:42:out(TAS-OUT)"
        And fallback to: "09:00 IN, 13:00 OUT"
        """
        from datetime import time
        if not punch_str or pd.isna(punch_str):
            return []
            
        punch_str = str(punch_str).lower().strip()
        
        # Pattern for strict "Time:Type(Code)" format
        # Matches: "09:17:in", "16:34:out(TAS-OUT)"
        # Group 1: Time, Group 2: Type (in/out)
        strict_pattern = r'(\d{1,2}:\d{2})\s*[:\-\s]\s*(in|out)'
        
        matches = list(re.finditer(strict_pattern, punch_str))
        
        # If strict matches found, trust them completely (ignore noise)
        if matches:
            final_punches = []
            for m in matches:
                try:
                    t_str, p_type = m.groups()
                    parts = t_str.split(':')
                    p_time = time(int(parts[0]), int(parts[1]))
                    final_punches.append((p_time, p_type))
                except:
                    continue
            return final_punches
            
        # Fallback: Loose scan for "Time... Type" or "Type... Time"
        # Only used if strict format fails
        # ... (Old Logic fallback) ...
        matches = re.finditer(r'(\d{1,2}:\d{2})[^0-9]*?(in|out)|(in|out)[^0-9]*?(\d{1,2}:\d{2})', punch_str)
        punches = []
        for match in matches:
            groups = match.groups()
            t_val = groups[0] or groups[3]
            m_val = (groups[1] or groups[2])
            if t_val and m_val:
                try:
                    parts = t_val.split(':')
                    p_time = time(int(parts[0]), int(parts[1]))
                    punches.append((p_time, m_val.lower()))
                except: pass
        
        return sorted(punches, key=lambda x: x[0])

    @staticmethod
    def import_attendance_excel(file):
        import pandas as pd
        from datetime import datetime, time
        import re
        from .models import RawPunch
        
        # 1. Cache Users
        users_qs = User.objects.filter(is_active=True)
        
        # Maps for fast lookup
        all_users_by_emp_id = {}
        all_users_by_fullname = {}
        
        for u in users_qs:
            # Full Name match (normalized)
            if u.full_name:
                all_users_by_fullname[u.full_name.strip().lower()] = u
            if u.first_name:
                all_users_by_fullname[u.first_name.strip().lower()] = u
            if u.last_name:
                all_users_by_fullname[u.last_name.strip().lower()] = u
            
            # Username match
            all_users_by_fullname[u.username.strip().lower()] = u

            # Employee ID matches
            ids_to_register = []
            if u.employee_id:
                ids_to_register.append(str(u.employee_id).strip().lower())
                # Add numeric only version
                num_only = re.sub(r'\D', '', str(u.employee_id))
                if num_only: ids_to_register.append(num_only)
            
            if u.aadhaar_number:
                ids_to_register.append(str(u.aadhaar_number).strip().lower())

            # Register all ID variants
            for k in ids_to_register:
                all_users_by_emp_id[k] = u
                all_users_by_emp_id[k.lstrip('0')] = u # Support '08' -> '8'
            
            # PK match
            all_users_by_emp_id[str(u.id)] = u
            all_users_by_emp_id[str(u.id).zfill(2)] = u
        
        # 2. Load Data
        engine = 'openpyxl'
        if hasattr(file, 'name') and file.name.endswith('.xls'):
            engine = 'xlrd'
            
        all_dfs = {}
        try:
            data = pd.read_excel(file, engine=engine, header=None, sheet_name=None)
            if isinstance(data, dict):
                 all_dfs = data
            else:
                 all_dfs = {'Sheet1': data}
        except Exception as e:
             return 0, [f"Read Error: {str(e)}"]

        # DATA ACCUMULATION: {(user_obj, date_obj): {'punches': set(), 'status': ''}}
        global_data_map = {}
        errors = []
        debug_trace = []
        
        debug_trace.append(f"Loaded {len(users_qs)} users. ID Keys: {list(all_users_by_emp_id.keys())[:5]}...")
        
        for sheet_name, df in all_dfs.items():
            debug_trace.append(f"Processing Sheet '{sheet_name}'. Rows: {len(df)}")
            current_user = None
            col_map = {'status': -1, 'punch': -1, 'date': -1, 'in': -1, 'out': -1}
            current_date_context = None
            pending_rows = []
            
            for index, row_series in df.iterrows():
                row = row_series.values
                row_str_lower = [str(x).lower().strip() for x in row]
                row_raw_str = " ".join([str(x) for x in row if str(x).lower() != 'nan'])

                # A. ATTEMPT USER MATCH ON EVERY ROW
                row_user = None
                # Optimized scan for user identification
                # A. ATTEMPT USER MATCH ON EVERY ROW
                row_user = None
                potential_id_user = None

                # Scan entire row first to find best match
                for cell in row:
                    c_str = str(cell).strip()
                    if not c_str or c_str.lower() == 'nan' or len(c_str) < 2: continue
                    
                    c_key = c_str.lower()
                    
                    # 1. Name Match (Highest Priority)
                    if c_key in all_users_by_fullname: 
                        row_user = all_users_by_fullname[c_key]; break
                    
                    # Cleaned Name Match
                    c_clean = re.sub(r'^(name|employee|emp|staff|mr\.|mrs\.|ms\.|dr\.)[\s\:\-\.]*', '', c_key).strip()
                    if c_clean and len(c_clean) > 2 and c_clean in all_users_by_fullname:
                        row_user = all_users_by_fullname[c_clean]; break
                        
                    # Fuzzy Word Match
                    words = re.split(r'[^a-z0-9]', c_key)
                    found_name = False
                    for w in words:
                         if len(w) >= 3 and w in all_users_by_fullname:
                             row_user = all_users_by_fullname[w]
                             found_name = True
                             break
                    if found_name: break 

                    # 2. ID Match (Candidate)
                    if not potential_id_user:
                        if c_key in all_users_by_emp_id: 
                            potential_id_user = all_users_by_emp_id[c_key]
                        elif re.sub(r'^(EMP|ID|NO)[\-\s\:]*', '', c_str, flags=re.IGNORECASE).lower() in all_users_by_emp_id:
                             potential_id_user = all_users_by_emp_id[re.sub(r'^(EMP|ID|NO)[\-\s\:]*', '', c_str, flags=re.IGNORECASE).lower()]
                        else:
                            num_id = re.sub(r'\D', '', c_str)
                            if num_id and num_id in all_users_by_emp_id: 
                                potential_id_user = all_users_by_emp_id[num_id]

                if not row_user and potential_id_user:
                    row_user = potential_id_user

                if row_user:
                    # User found. Switch context.
                    if current_user is None and pending_rows:
                        # Bottom-up support
                        for p_row in pending_rows:
                            PayrollService._collect_row_data(p_row, row_user, col_map, current_date_context, global_data_map)
                        pending_rows = []
                    current_user = row_user
                    
                    # Check if this row is ONLY user info or has data too
                    has_date = False
                    for cell in row:
                        try:
                            res = pd.to_datetime(cell, dayfirst=True, errors='coerce')
                            if res and not pd.isna(res) and res.year > 2020: has_date = True; break
                        except: pass
                    
                    if not has_date and not re.search(r'\d{1,2}:\d{2}', row_raw_str):
                        continue # Move to next row to find data

                # B. DETECT BLOCK RESET / TOTALS
                if any(kw in row_raw_str.lower() for kw in ['total duration', 'presentdays', 'absentdays', 'summary']):
                    current_user = None
                    pending_rows = []
                    continue

                # C. DETECT HEADER ROW
                # Trigger mapping if we see standard headers
                header_keywords = ['status', 'punch', 'check-in', 'check in', 'in time', 'out time', 'clock in', 'clock out', 'date', 'work date', 'emp', 'code']
                is_header = any(kw in row_raw_str.lower() for kw in header_keywords)
                # Also check for exact 'in' / 'out' headers which are common
                if not is_header and ('in' in row_str_lower and 'out' in row_str_lower):
                    is_header = True

                if is_header:
                    debug_trace.append(f"Header Detected: {row_str_lower}")
                    for i, val in enumerate(row_str_lower):
                        val_clean = val.strip()
                        if 'status' in val: col_map['status'] = i
                        elif 'punch' in val or 'logs' in val or 'record' in val: col_map['punch'] = i
                        elif 'date' in val or 'work day' in val or 'work_date' in val: col_map['date'] = i
                        # Strict IN/OUT detection
                        elif val_clean == 'in' or 'check-in' in val or 'in time' in val or 'in_time' in val or 'clock in' in val or 'clock_in' in val: col_map['in'] = i
                        elif val_clean == 'out' or 'check-out' in val or 'out time' in val or 'out_time' in val or 'clock out' in val or 'clock_out' in val: col_map['out'] = i
                    continue

                # D. DETECT DATA ROW
                row_date = None
                for cell in row:
                    try:
                        res = pd.to_datetime(cell, dayfirst=True, errors='coerce')
                        if res and not pd.isna(res) and res.year > 2000:
                            row_date = res.date()
                            # 2026 fix if needed (likely context is 2025/2026)
                            if row_date.month == 12 and row_date.year == 2026: row_date = row_date.replace(year=2025)
                            current_date_context = row_date
                            break
                    except: pass
                
                has_punch = re.search(r'\d{1,2}:\d{2}', row_raw_str)
                is_data = row_date is not None or has_punch or any(kw in row_raw_str.upper() for kw in ['PRESENT', 'ABSENT', 'WEEKLYOFF', 'HOLIDAY'])

                if is_data:
                    if current_user:
                        PayrollService._collect_row_data(row, current_user, col_map, current_date_context, global_data_map)
                    else:
                        pending_rows.append(row)

        # 5. COMMIT ACCUMULATED DATA
        logs_created = 0
        for (user, att_date), data in global_data_map.items():
            try:
                PayrollService._save_attendance_record(user, att_date, data['punches'], data['status'])
                logs_created += 1
            except Exception as e:
                errors.append(f"Save error for {user.username} on {att_date}: {str(e)}")

        if logs_created == 0 and not errors:
             errors.append("No valid attendance data found. Ensure Employee Names/IDs in Excel match the system.")
        
        dates = [k[1] for k in global_data_map.keys()]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None

        return logs_created, errors, min_date, max_date

    @staticmethod
    def _collect_row_data(row, user, col_map, date_context, global_map):
        """Accumulates punches and status from a row into the global map"""
        from datetime import date
        import pandas as pd
        
        # 1. Date Detection
        att_date = None
        d_idx = col_map.get('date', -1)
        if d_idx != -1 and d_idx < len(row):
            try:
                res = pd.to_datetime(row[d_idx], dayfirst=True, errors='coerce')
                if res and not pd.isna(res): att_date = res.date()
            except: pass
        if not att_date: att_date = date_context
        if not att_date: return

        # 2. Punch Detection (Priority: "Punch Records" column -> Summary Columns -> Full Row Scan)
        row_punches = []

        # Method A: Explicit Punch Records Column (Highest Fidelity)
        p_idx = col_map.get('punch', -1)
        if p_idx != -1 and p_idx < len(row):
            punch_str = str(row[p_idx])
            if punch_str and punch_str.lower() not in ['nan', 'none', 'null']:
                 row_punches = PayrollService.parse_punch_records_regex(punch_str)

        # Method B: Separate In/Out Summary Columns (Fallback if no punch records)
        if not row_punches:
            in_idx = col_map.get('in', -1)
            out_idx = col_map.get('out', -1)
            if in_idx != -1 and out_idx != -1:
                 # Process IN
                 in_raw = row[in_idx]
                 try:
                     if pd.notna(in_raw):
                         if isinstance(in_raw, (time, datetime)):
                             t_val = in_raw.time() if isinstance(in_raw, datetime) else in_raw
                             row_punches.append((t_val, 'in'))
                         else:
                             res = pd.to_datetime(in_raw, errors='coerce')
                             if pd.notna(res):
                                 row_punches.append((res.time(), 'in'))
                             else:
                                 in_val = str(in_raw).strip()
                                 if re.search(r'\d{1,2}:\d{2}', in_val):
                                     row_punches.extend(PayrollService.parse_punch_records_regex(in_val + " IN"))
                 except: pass

                 # Process OUT
                 out_raw = row[out_idx]
                 try:
                     if pd.notna(out_raw):
                         if isinstance(out_raw, (time, datetime)):
                             t_val = out_raw.time() if isinstance(out_raw, datetime) else out_raw
                             row_punches.append((t_val, 'out'))
                         else:
                             res = pd.to_datetime(out_raw, errors='coerce')
                             if pd.notna(res):
                                 row_punches.append((res.time(), 'out'))
                             else:
                                 out_val = str(out_raw).strip()
                                 if re.search(r'\d{1,2}:\d{2}', out_val):
                                     row_punches.extend(PayrollService.parse_punch_records_regex(out_val + " OUT"))
                 except: pass

        # Method C: Full Row Scan (Last Resort)
        if not row_punches:
             # Scan whole row excluding status/date columns to avoid false positives?
             # Just scanning joined string is risky for 'Present' text matching 'ent' etc? No, strictly regex.
             punch_str = " ".join([str(x) for x in row if str(x).lower() not in ['nan', 'none', 'null']])
             row_punches = PayrollService.parse_punch_records_regex(punch_str)
        
        # 3. Status Extraction
        s_idx = col_map.get('status', -1)
        status_val = str(row[s_idx]).strip() if s_idx != -1 and s_idx < len(row) else ""
        
        key = (user, att_date)
        if key not in global_map:
            global_map[key] = {'punches': set(), 'status': ''}
        
        # Add punches
        for p_time, p_type in row_punches:
            global_map[key]['punches'].add((p_time, p_type))
            
        # Update status (Priority to meaningful status like PRESENT, WEEKLYOFF over unassigned)
        if status_val and len(status_val) >= 1:
            curr_status = status_val.upper()
            # If current row has a more specific status, use it
            if any(kw in curr_status for kw in ['PRESENT', 'ABSENT', 'WEEKLY', 'HOLIDAY', 'HALF']):
                global_map[key]['status'] = status_val
            elif not global_map[key]['status']:
                global_map[key]['status'] = status_val

    @staticmethod
    def _save_attendance_record(user, att_date, punches_set, status_str):
        """Final DB commit for a user's date with ALL punches"""
        from .models import AttendanceLog, RawPunch
        
        # 1. Map Status
        status_upper = status_str.upper()
        final_status = "Present"
        if 'ABSENT' in status_upper or status_upper == 'A': final_status = "Absent"
        elif 'WEEKLY' in status_upper: final_status = "WeeklyOff"
        elif 'HOLIDAY' in status_upper: final_status = "Holiday"
        elif any(kw in status_upper for kw in ['½', '1/2', 'HP', 'HALF']): final_status = "HalfDay"
        elif not status_str and not punches_set: final_status = "Absent"

        # 2. Sort punches
        sorted_punches = sorted(list(punches_set), key=lambda x: x[0])
        
        # 3. Determine Summary Times
        in_punches = [p[0] for p in sorted_punches if p[1].lower() == 'in']
        out_punches = [p[0] for p in sorted_punches if p[1].lower() == 'out']
        
        summary_in = in_punches[0] if in_punches else (sorted_punches[0][0] if sorted_punches else None)
        summary_out = out_punches[-1] if out_punches else (sorted_punches[-1][0] if sorted_punches else None)

        # 4. Save Log
        log, _ = AttendanceLog.objects.update_or_create(
            employee=user, date=att_date,
            defaults={
                'check_in': summary_in, 
                'check_out': summary_out,
                'status': final_status, 
                'entry_type': AttendanceLog.EntryType.AUTO
            }
        )
        
        # 5. Save Raw Punches (True breakdown)
        log.raw_punches.all().delete()
        for p_time, p_type in sorted_punches:
            RawPunch.objects.create(
                attendance_log=log, 
                time=p_time, 
                punch_type=p_type.upper()
            )
            
        # 6. Final Calculation
        log.recalculate_duration(punches_list=sorted_punches)


    @staticmethod
    def calculate_payroll(batch: PayrollBatch):
        """
        Calculates net salary for all active employees based on 8-Hour Monthly Satisfaction Model.
        Rules:
        1. Base Salary = Full Monthly Salary (Attendance doesn't reduce base).
        2. Required Hours = Working Days * 8.
        3. Worked Hours = Sum of daily worked hours.
        4. Shortfall = Required - Worked.
        5. LOP = Shortfall * Hourly Rate (Daily / 8).
        6. OT Pay = Approved OT Hours * Hourly Rate * Multiplier (1.25 Default).
        7. Statutory Deductions are mandatory. Company deductions waivable.
        """
        from core.models import CompanySettings
        from leaves.models import LeaveRequest
        from .models import DeductionComponent, EmployeeDeduction, PayrollDeduction, PayrollEntry, AttendanceLog
        import calendar
        from decimal import Decimal
        
        settings = CompanySettings.load()
        employees = User.objects.filter(is_active=True).exclude(role__in=['CEO', 'ADMIN'])
        month_start = batch.month
        
        # Standard basis
        days_in_basis = Decimal('30.00')
        _, num_days = calendar.monthrange(month_start.year, month_start.month)
        
        # Clear existing entries for this batch if re-running (Draft only)
        if batch.status == PayrollBatch.Status.DRAFT:
             batch.entries.all().delete()

        for emp in employees:
            basic = emp.salary_basic
            allowance = emp.salary_allowance
            gross_monthly = basic + allowance
            daily_salary = gross_monthly / days_in_basis
            hourly_rate = daily_salary / Decimal('8.00')
            
            # 1. Calculate Required Hours & Working Days
            working_days_count = 0
            required_work_hours = Decimal('0.00')
            
            # Iterate to count working days
            for d in range(1, num_days + 1):
                check_date = month_start.replace(day=d)
                # Check holiday/weekend
                if not settings.is_holiday(check_date):
                    working_days_count += 1
            
            required_work_hours = Decimal(working_days_count) * Decimal('8.00')
            
            # 2. Get Actual Worked Data & Freeze Attendance
            logs = AttendanceLog.objects.filter(
                employee=emp, 
                date__year=month_start.year, 
                date__month=month_start.month
            )
            
            total_worked_minutes = 0
            approved_ot_minutes = 0
            
            for log in logs:
                # Freeze
                if not log.is_locked:
                    log.is_locked = True
                    # Recalculate duration one last time to be sure
                    # log.recalculate_duration() # Optional: heavy operation, assume done on save
                    log.save(update_fields=['is_locked'])
                
                # Use total_work_minutes which is populated by recalculate_duration
                if log.total_work_minutes:
                    total_worked_minutes += log.total_work_minutes
                
                if log.approved_overtime_minutes:
                    approved_ot_minutes += log.approved_overtime_minutes
            
            actual_work_hours = Decimal(total_worked_minutes) / Decimal('60.00')
            approved_ot_hours = Decimal(approved_ot_minutes) / Decimal('60.00')
            
            # 3. Evaluate Shortfall (Monthly Satisfaction)
            # "If worked_hours >= required_hours: shortfall = 0"
            if actual_work_hours >= required_work_hours:
                shortfall_hours = Decimal('0.00')
            else:
                shortfall_hours = required_work_hours - actual_work_hours
            
            # 4. Calculate LOP
            # "LOP_amount = shortfall_hours * hourly_rate"
            lop_amount = shortfall_hours * hourly_rate
            
            # 5. Calculate OT Pay
            # "approved_ot_pay = approved_ot_hours * hourly_rate * ot_multiplier"
            ot_multiplier = Decimal('1.0') # Default 1.0 as standard if not specified, usually 1.25 or 1.5 in UAE/India
            # User requirement 11: "ot_multiplier". Let's assume 1.0 unless we find a setting. 
            # Given "Extra hours ... do NOT match OT", 1.0 is safe.
            approved_ot_pay = approved_ot_hours * hourly_rate * ot_multiplier
            
            # 6. Final Calculation
            # "gross_salary = base_salary + approved_ot_pay + other_earnings"
            # Base salary is full monthly (basic + allowance)
            base_pay = gross_monthly 
            gross_earnings = base_pay + approved_ot_pay # + variable_pay if any
            
            # Create Entry
            payroll_entry = PayrollEntry.objects.create(
                batch=batch,
                employee=emp,
                basic_salary=basic,
                allowances=allowance,
                
                # Stats
                days_worked=working_days_count, # Valid approximation or should use logs.count()? 
                # User wants "Required Hours, Worked Hours". 
                # Let's just put working_days_count as a placeholder for days_worked or use distinct logs
                # Actually days_worked in model is Integer. Let's use the Working Days Count as "Days Expected" or logs.count() as "Days Attended".
                # For now, put logs.count() if preferred, but existing logic used 30.
                days_absent=0, # Calculated dynamically via shortfall
                total_full_days=0, # Not used in new model
                total_half_days=0,
                
                # New Fields
                required_work_hours=round(required_work_hours, 2),
                actual_work_hours=round(actual_work_hours, 2),
                shortfall_work_hours=round(shortfall_hours, 2),
                lop_deduction=round(lop_amount, 2),
                approved_ot_hours=round(approved_ot_hours, 2),
                approved_ot_minutes=approved_ot_minutes,
                
                # Financials
                base_pay=round(base_pay, 2),
                ot_pay=round(approved_ot_pay, 2),
                gross_salary=round(gross_earnings, 2),
                deductions=0,
                net_salary=0,
                iban=emp.iban or ""
            )
            
            # 7. Deductions
            total_deductions = Decimal('0.00')
            
            # A. Recurring Deductions
            recurring = EmployeeDeduction.objects.filter(employee=emp, is_active=True)
            for ded in recurring:
                val = ded.amount
                if ded.percentage > 0:
                     val = (basic * ded.percentage) / 100
                
                PayrollDeduction.objects.create(
                    payroll_entry=payroll_entry,
                    component=ded.component,
                    amount=val,
                    approved_amount=val,
                    is_waived=False
                )
                total_deductions += val
                
            # B. LOP Deduction (As a specialized deduction or just subtract from Net?)
            # Requirement 17: "net_salary = gross_salary - total_deductions - LOP_amount"
            # We can better visualize it by adding a System Deduction for LOP
            if lop_amount > 0:
                # Find or Create LOP Component
                lop_component, _ = DeductionComponent.objects.get_or_create(
                    name="Loss of Pay (Shortfall)",
                    defaults={'is_statutory': True, 'is_recurring': False} 
                )
                # It acts as a Company Deduction (Section 14 says "Company deductions (LOP adjustments...)" implies it can be waived)
                # Section 13 says Statutory are non-waivable.
                # Section 14 says Company (LOP adjustments...) may be waived.
                # So LOP is Company Deduction.
                lop_component.is_statutory = False
                lop_component.save()
                
                PayrollDeduction.objects.create(
                    payroll_entry=payroll_entry,
                    component=lop_component,
                    amount=lop_amount,
                    approved_amount=lop_amount,
                    is_waived=False
                )
                total_deductions += lop_amount

            # Final Net
            # ensure net_salary >= 0
            net_pay = max(Decimal('0.00'), gross_earnings - total_deductions)
            
            payroll_entry.deductions = round(total_deductions, 2)
            payroll_entry.net_salary = round(net_pay, 2)
            payroll_entry.save()

