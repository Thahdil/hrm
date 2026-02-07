from django import forms
from .models import TicketRequest

class TicketRequestForm(forms.ModelForm):
    class Meta:
        model = TicketRequest
        fields = ['destination', 'travel_date', 'return_date', 'is_encashment']
        widgets = {
            'destination': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. DXB to COK'}),
            'travel_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'return_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'is_encashment': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
