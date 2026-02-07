from django.db import models
from django.conf import settings

class AttendanceLog(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_logs')
    date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    is_absent = models.BooleanField(default=False)
    
    # Compliance & Duration
    total_work_minutes = models.IntegerField(default=0, help_text="Total minutes worked")
    is_compliant = models.BooleanField(default=False, help_text="True if > 8 hours (480 mins)")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Status(models.TextChoices):
        PRESENT = "Present", "Present"
        ABSENT = "Absent", "Absent"
        WEEKLY_OFF = "WeeklyOff", "Weekly Off"
        HOLIDAY = "Holiday", "Holiday"
        HALFDAY = "HalfDay", "Half Day"
        DISPUTED = "DISPUTED", "Disputed"
        VOID = "VOID", "Void"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    
    def _get_cleaned_punches(self, punches_data=None):
        """
        Smart Cleaning Protocol:
        1. IN... IN: 
           - If < 20 mins diff: Keep FIRST (Assume double-tap/jitter).
           - If > 20 mins diff: Keep LATEST (Assume 'Ghost Out' / Missed Punch).
        2. OUT... OUT:
           - If < 20 mins diff: Extend to LATEST (Assume double-tap).
           - If > 20 mins diff: Ignore subsequent (Orphan).
        """
        from datetime import datetime, timedelta
        
        if punches_data is None:
            punches = list(self.raw_punches.all().order_by('time'))
            if not punches: return []
            punches_data = [(p.time, p.punch_type.lower()) for p in punches]

        # 1. Sort by time
        sorted_punches = sorted(punches_data, key=lambda x: x[0])
        
        cleaned = []
        last_in = None
        # Helper to convert time to full datetime for diffing (dummy date)
        def to_dt(t): return datetime.combine(datetime.min, t)
        
        for p_time, p_type in sorted_punches:
            if p_type == 'in':
                if last_in:
                    # check gap
                    diff = to_dt(p_time) - to_dt(last_in)
                    if diff.total_seconds() < 1200: # 20 mins
                        # Jitter: Ignore this new punch, keep the earlier IN
                        continue
                    else:
                        # Large gap: Ghost Out. Overwrite header.
                        last_in = p_time
                else:
                    last_in = p_time
                
            elif p_type == 'out':
                if last_in:
                    # Valid Session
                    cleaned.append((last_in, 'in'))
                    cleaned.append((p_time, 'out'))
                    last_in = None
                else:
                    # Orphan OUT. 
                    # Check if we can extend the PREVIOUS session's OUT?
                    # We need to look at 'cleaned' list.
                    if cleaned and cleaned[-1][1] == 'out':
                        prev_out = cleaned[-1][0]
                        diff = to_dt(p_time) - to_dt(prev_out)
                        if diff.total_seconds() < 1200: # 20 mins
                            # Extend previous session
                            cleaned.pop() # remove old out
                            cleaned.append((p_time, 'out')) # new out
                    
        return cleaned

    def _calculate_total_minutes(self, cleaned_punches):
        """
        Strict calculation based on user formula:
        1. Subtract In from Out for each session (hours and minutes separately)
        2. Sum all hours and minutes
        3. Convert every 60 mins into 1 hour
        """
        agg_hours = 0
        agg_minutes = 0
        
        last_in = None
        for p_time, p_type in cleaned_punches:
            if p_type == 'in':
                last_in = p_time
            elif p_type == 'out' and last_in:
                # Calculate diff for this session
                h_diff = p_time.hour - last_in.hour
                m_diff = p_time.minute - last_in.minute
                
                # Handle negative minutes (borrow hour)
                if m_diff < 0:
                    m_diff += 60
                    h_diff -= 1
                
                # Handle midnight crossover (e.g. 23:00 to 01:00)
                if h_diff < 0:
                    h_diff += 24
                
                # Add to aggregate totals
                agg_hours += h_diff
                agg_minutes += m_diff
                
                last_in = None
        
        # Final conversion
        extra_hours = agg_minutes // 60
        final_minutes = agg_minutes % 60
        final_hours = agg_hours + extra_hours
        
        return (final_hours * 60) + final_minutes

    @property
    def hours_str(self):
        """Returns duration in 'X hrs Y mins' format following the 'Raw Punch Truth' logic"""
        status_upper = str(self.status or "").upper()
        # 0. Zero-Duration Rule (Strictly enforced as per user request)
        if any(kw in status_upper for kw in ['ABSENT', 'WEEKLYOFF', 'HOLIDAY']):
            return "0 hrs 0 mins"

        cleaned = self._get_cleaned_punches()
        if not cleaned:
            # Fallback to cached total_work_minutes
            if self.total_work_minutes > 0:
                h = self.total_work_minutes // 60
                m = self.total_work_minutes % 60
                return f"{h} hrs {m} mins"
            
            # Half-day fallback logic
            if any(kw in status_upper for kw in ['HALFDAY', '½', '1/2']):
                return "4 hrs 0 mins"
            return "0 hrs 0 mins"

        total_mins = self._calculate_total_minutes(cleaned)
        final_h = total_mins // 60
        rem_m = total_mins % 60
        return f"{final_h} hrs {rem_m} mins"

    @property
    def segments(self):
        """Returns paired IN/OUT segments for breakdown using the 'Raw Punch Truth' logic"""
        status_upper = str(self.status).upper()
        if any(kw in status_upper for kw in ['ABSENT', 'WEEKLYOFF', 'HOLIDAY']):
            return []

        cleaned = self._get_cleaned_punches()
        if not cleaned:
            return []

        segments_list = []
        last_in = None
        for p_time, p_type in cleaned:
            if p_type == 'in':
                last_in = p_time
            elif p_type == 'out' and last_in:
                h_diff = p_time.hour - last_in.hour
                m_diff = p_time.minute - last_in.minute
                if m_diff < 0:
                    m_diff += 60
                    h_diff -= 1
                segments_list.append({
                    'in': last_in,
                    'out': p_time,
                    'duration': f"{h_diff} hrs {m_diff} mins",
                    'minutes': (h_diff * 60) + m_diff
                })
                last_in = None
        return segments_list

    @property
    def shortfall_minutes(self):
        """Calculates shortfall relative to 8 hours (480 mins)"""
        status_upper = str(self.status or "").upper()
        # Only calculate for working statuses
        if any(kw in status_upper for kw in ['PRESENT', 'HALFDAY', '½', '1/2']):
             # Threshold for Present is 480, HalfDay is 240
             threshold = 480
             if any(kw in status_upper for kw in ['HALFDAY', '½', '1/2']):
                  threshold = 240
             
             if self.total_work_minutes < threshold:
                  return threshold - self.total_work_minutes
        return 0

    @property
    def shortfall_str(self):
        
        """Human readable shortfall (e.g. 1 hr 30 mins short)"""
        mins = self.shortfall_minutes
        if mins <= 0:
            return ""
        h = mins // 60
        m = mins % 60
        if h > 0:
            return f"{h} hr {m} mins"
        return f"{m} mins"

    class EntryType(models.TextChoices):
        AUTO = 'AUTO', 'Auto Punch'
        MANUAL = 'MANUAL', 'Manual Entry'

    entry_type = models.CharField(max_length=10, choices=EntryType.choices, default=EntryType.AUTO)
    remarks = models.TextField(blank=True, null=True, help_text="Reason for manual entry or adjustments")

    @property
    def is_holiday(self):
        from core.models import CompanySettings
        settings = CompanySettings.load()
        return settings.is_holiday(self.date)

    def save(self, *args, **kwargs):
        # Sync is_absent with status
        status_upper = str(self.status).upper()
        if 'ABSENT' in status_upper:
            self.is_absent = True
        elif 'PRESENT' in status_upper:
            self.is_absent = False
            
        # COMPLIANCE LOGIC: 8 hours standard, 4 hours for Half Day
        threshold = 480
        if any(kw in status_upper for kw in ['HALFDAY', '½', '1/2']):
            threshold = 240
        
        # Priority 1: If they are working (PRESENT/HALFDAY), they MUST meet the threshold to be compliant
        if any(kw in status_upper for kw in ['PRESENT', 'HALFDAY', '½', '1/2']):
             self.is_compliant = self.total_work_minutes >= threshold
        # Priority 2: If it's a Holiday/WeeklyOff and they AREN'T working, it's compliant (0 hours allowed)
        elif any(kw in status_upper for kw in ['WEEKLY', 'HOLIDAY']) or self.is_holiday:
             self.is_compliant = True
        # Priority 3: Fallback (usually for Absent or unknown statuses)
        else:
             self.is_compliant = self.total_work_minutes >= threshold
             
        super().save(*args, **kwargs)

        if self.entry_type == self.EntryType.MANUAL and self.pk:
            if self.check_in and self.check_out:
                # If times changed, sync RawPunch records
                from .models import RawPunch
                # For manual, we strictly want one IN (check_in) and one OUT (check_out)
                self.raw_punches.all().delete()
                RawPunch.objects.create(attendance_log=self, time=self.check_in, punch_type='IN')
                RawPunch.objects.create(attendance_log=self, time=self.check_out, punch_type='OUT')
                # Recalculate duration to ensure total_work_minutes is updated
                self.recalculate_duration(skip_save=True) # skip_save to avoid recursion since we are in save()
                super().save(*args, **kwargs) # Save again with new minutes

    def recalculate_duration(self, skip_save=False, punches_list=None):
        """
        Update total_work_minutes using 'Raw Punch Truth'.
        Priority: 
        1. If punches exist, calculate duration regardless of status label.
        2. If duration > 0, override 'Absent' status.
        3. If no punches, respect textual status (Holiday/WeeklyOff/Absent).
        """
        status_upper = str(self.status or "").upper()
        
        # Get Cleaned Punches (using Ghost Out protocol)
        cleaned = self._get_cleaned_punches(punches_data=punches_list)
        
        if not cleaned:
            # No punches found. Respect the status label.
            if any(kw in status_upper for kw in ['HALFDAY', '½', '1/2']):
                self.total_work_minutes = 240
            else:
                self.total_work_minutes = 0
            
            if 'ABSENT' in status_upper:
                self.is_absent = True
            
            # Sync summary fields to None since no punches
            if self.entry_type != self.EntryType.MANUAL:
                self.check_in = None
                self.check_out = None
                
            if not skip_save: self.save()
            return self.total_work_minutes

        # We have punches -> Calculate Duration (Strict Formula)
        total_mins = self._calculate_total_minutes(cleaned)
        
        self.total_work_minutes = total_mins
        
        if total_mins > 0:
            self.is_absent = False
            # If currently marked absent/void but has work time, auto-correct to Present
            if any(kw in status_upper for kw in ['ABSENT', 'A', 'VOID']):
                self.status = self.Status.PRESENT
        else:
            # Punches exist but 0 duration (e.g. In-Out same minute)?
            # Keep existing status or set to Absent if minimal?
            # For now, let's allow 0 mins if punches exist (e.g. came in and left immediately)
            pass
        
        # Sync check_in/out summary fields
        if self.entry_type != self.EntryType.MANUAL:
            in_punches = [p[0] for p in cleaned if p[1] == 'in']
            out_punches = [p[0] for p in cleaned if p[1] == 'out']
            # Reset
            self.check_in = None
            self.check_out = None
            
            if in_punches: self.check_in = in_punches[0]
            if out_punches: self.check_out = out_punches[-1]
            # Fallback if types missing (unlikely with clean logic but safe)
            if not self.check_in and cleaned: self.check_in = cleaned[0][0]
            if not self.check_out and cleaned: self.check_out = cleaned[-1][0]

        if not skip_save: self.save()
        return self.total_work_minutes

    class Meta:
        unique_together = ('employee', 'date')

class RawPunch(models.Model):
    attendance_log = models.ForeignKey(AttendanceLog, on_delete=models.CASCADE, related_name='raw_punches')
    time = models.TimeField()
    punch_type = models.CharField(max_length=10, blank=True, help_text="IN, OUT, or raw code")
    
    class Meta:
        ordering = ['time']

class PayrollBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"
        VOID = "VOID", "Void"

    month = models.DateField(help_text="First day of the month for this payroll")
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    sif_file = models.FileField(upload_to='sif_files/', null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    def __str__(self):
        return f"Payroll {self.month.strftime('%B %Y')}"

class PayrollEntry(models.Model):
    batch = models.ForeignKey(PayrollBatch, on_delete=models.CASCADE, related_name='entries')
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    
    # Financials
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2)
    variable_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Overtime, Commissions, Bonuses")
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Attendance Stats
    days_worked = models.IntegerField(default=30)
    days_absent = models.IntegerField(default=0)

    # WPS Info
    iban = models.CharField(max_length=34) # Decrypted storage for SIF generation or keep valid chars
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PROCESSED = "PROCESSED", "Processed"
        HELD = "HELD", "Held"
        PAID = "PAID", "Paid"
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    def __str__(self):
        return f"{self.employee.full_name} - {self.net_salary}"
