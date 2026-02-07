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
                for cell in row:
                    c_str = str(cell).strip()
                    if not c_str or c_str.lower() == 'nan' or len(c_str) < 2: continue
                    
                    c_key = c_str.lower()
                    
                    # 1. Primary Match: Full Name (as requested)
                    if c_key in all_users_by_fullname: 
                        row_user = all_users_by_fullname[c_key]; break
                    
                    # 2. Secondary Match: ID/Code
                    if c_key in all_users_by_emp_id: row_user = all_users_by_emp_id[c_key]; break
                    
                    clean_id = re.sub(r'^(EMP|ID|NO)[\-\s\:]*', '', c_str, flags=re.IGNORECASE)
                    if clean_id.lower() in all_users_by_emp_id: row_user = all_users_by_emp_id[clean_id.lower()]; break
                    
                    num_id = re.sub(r'\D', '', c_str)
                    if num_id and num_id in all_users_by_emp_id: row_user = all_users_by_emp_id[num_id]; break

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
                is_header = any(kw in row_str_lower for kw in ['status', 'punch', 'check-in', 'date', 'work date'])
                if is_header:
                    for i, val in enumerate(row_str_lower):
                        if 'status' in val: col_map['status'] = i
                        elif 'punch' in val or 'logs' in val or 'record' in val: col_map['punch'] = i
                        elif 'date' in val or 'day' in val: col_map['date'] = i
                        elif 'check-in' in val or 'in time' in val or 'in_time' in val: col_map['in'] = i
                        elif 'check-out' in val or 'out time' in val or 'out_time' in val: col_map['out'] = i
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
        
        return logs_created, errors

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

        # 2. Punch Detection (Merged or Separate Columns)
        row_punches = []
        
        # Method A: Separate In/Out Columns
        in_idx = col_map.get('in', -1)
        out_idx = col_map.get('out', -1)
        if in_idx != -1 and out_idx != -1:
             in_val = str(row[in_idx]).strip()
             out_val = str(row[out_idx]).strip()
             if re.search(r'\d{1,2}:\d{2}', in_val):
                  row_punches.extend(PayrollService.parse_punch_records_regex(in_val + " IN"))
             if re.search(r'\d{1,2}:\d{2}', out_val):
                  row_punches.extend(PayrollService.parse_punch_records_regex(out_val + " OUT"))

        # Method B: Merged Punch Column or Full Row Scan
        if not row_punches:
            p_idx = col_map.get('punch', -1)
            punch_str = str(row[p_idx]) if p_idx != -1 and p_idx < len(row) else ""
            if not punch_str or punch_str.lower() in ['nan', 'none']:
                 # Fallback: scan whole row if no specific column matched
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
        Calculates net salary for all active employees for the batch month.
        Deducts salary for:
        1. Absent days (Full day deduction)
        2. Short work hours (Pro-rata deduction if < 8 hours/day)
        3. Unpaid Leave (Full day deduction)
        """
        from core.models import CompanySettings
        from leaves.models import LeaveRequest
        import calendar
        
        settings = CompanySettings.load()
        employees = User.objects.filter(is_active=True).exclude(role='CEO')
        month_start = batch.month
        
        # Standard basis for Indian Payroll calculation
        days_in_basis = Decimal('30.00')
        minutes_per_day = 480 # 8 hours
        
        _, num_days = calendar.monthrange(month_start.year, month_start.month)
        month_end = month_start.replace(day=num_days)

        for emp in employees:
            basic = emp.salary_basic
            allowance = emp.salary_allowance
            
            total_missing_minutes = 0
            absent_days_count = 0
            
            # Iterate through every day of the month to check compliance
            for d in range(1, num_days + 1):
                check_date = month_start.replace(day=d)
                
                # 1. Is it a holiday/weekend? (No deduction if not working)
                if settings.is_holiday(check_date):
                    continue
                
                # 2. Check for Leaves first (Approved leaves override attendance)
                leave = LeaveRequest.objects.filter(
                    employee=emp,
                    status=LeaveRequest.Status.APPROVED,
                    start_date__lte=check_date,
                    end_date__gte=check_date
                ).first()
                
                if leave:
                    if leave.leave_type.code == 'UNP': # Unpaid
                        total_missing_minutes += minutes_per_day
                        absent_days_count += 1
                    # Paid leaves (Annual/Sick) have 0 deduction
                    continue
                
                # 3. Check Attendance
                log = AttendanceLog.objects.filter(employee=emp, date=check_date).first()
                
                if not log or log.is_absent or log.status in ['Absent', 'A']:
                    # No work performed on a workday
                    total_missing_minutes += minutes_per_day
                    absent_days_count += 1
                elif not log.is_compliant:
                    # Short work hours - deduct the deficit
                    deficit = minutes_per_day - log.total_work_minutes
                    if deficit > 0:
                        total_missing_minutes += deficit
            
            # 4. Financial Calculation
            # Minute Rate = (Monthly Total / 30 days) / 480 minutes
            daily_rate = (basic + allowance) / days_in_basis
            minute_rate = daily_rate / Decimal(str(minutes_per_day))
            
            deductions = minute_rate * Decimal(total_missing_minutes)
            net = (basic + allowance) - deductions
            
            # Ensure net doesn't go below floor
            net = max(net, Decimal('0.00'))
            
            PayrollEntry.objects.create(
                batch=batch,
                employee=emp,
                basic_salary=basic,
                allowances=allowance,
                deductions=round(deductions, 2),
                net_salary=round(net, 2),
                days_worked=num_days - absent_days_count,
                days_absent=absent_days_count,
                iban=emp.iban or ""
            )
