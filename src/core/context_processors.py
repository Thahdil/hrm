from core.models import CompanySettings

def company_settings(request):
    settings = CompanySettings.load()
    return {
        'company_name': settings.name,
        'currency_symbol': settings.currency_symbol,
        'currency_code': settings.currency_code,
    }
