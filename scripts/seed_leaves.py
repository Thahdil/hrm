
import os
import django
import sys

# Setup Django Environment
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from leaves.models import LeaveType

def create_leaves():
    leaves = [
        {
            "name": "Annual Leave",
            "code": "ANN",
            "days": 30,
            "paid": True,
            "gender": "ALL",
            "min_service": 365,
            "cf": True
        },
        {
            "name": "Sick Leave",
            "code": "SCK",
            "days": 90,
            "paid": True, # Technically mixed, but base entitlement allows application
            "gender": "ALL",
            "min_service": 90, # Post probation
            "cf": False
        },
        {
            "name": "Maternity Leave",
            "code": "MAT",
            "days": 60,
            "paid": True,
            "gender": "Female",
            "min_service": 0,
            "cf": False
        },
        {
            "name": "Parental Leave",
            "code": "PAR",
            "days": 5,
            "paid": True,
            "gender": "ALL",
            "min_service": 0,
            "cf": False
        },
        {
            "name": "Bereavement Leave",
            "code": "BER",
            "days": 5, 
            "paid": True,
            "gender": "ALL",
            "min_service": 0,
            "cf": False
        },
        {
            "name": "Study Leave",
            "code": "STY",
            "days": 10,
            "paid": True,
            "gender": "ALL",
            "min_service": 730, # 2 Years
            "cf": False
        },
        {
            "name": "Hajj Leave",
            "code": "HAJ",
            "days": 30,
            "paid": False, # Unpaid
            "gender": "ALL",
            "min_service": 365,
            "cf": False
        }
    ]

    print("Initializing UAE Statutory Leave Types...")
    
    for l in leaves:
        obj, created = LeaveType.objects.update_or_create(
            name=l["name"],
            defaults={
                "code": l["code"],
                "days_entitlement": l["days"],
                "is_paid": l["paid"],
                "eligibility_gender": l["gender"],
                "min_service_days": l["min_service"],
                "is_carry_forward": l["cf"],
                "accrual_frequency": "ANNUAL"
            }
        )
        status = "Created" if created else "Updated"
        print(f" - {l['name']}: {status}")

if __name__ == "__main__":
    create_leaves()
