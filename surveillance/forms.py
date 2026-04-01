from django import forms
from django.contrib.auth.models import User
from .models import TargetPerson

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class':'form-control'}))
    password2 = forms.CharField(label='Repeat password', widget=forms.PasswordInput(attrs={'class':'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class':'form-control'}),
            'first_name': forms.TextInput(attrs={'class':'form-control'}),
            'last_name': forms.TextInput(attrs={'class':'form-control'}),
            'email': forms.EmailInput(attrs={'class':'form-control'}),
        }

    def clean_password2(self):
        cd = self.cleaned_data
        if 'password' in cd and 'password2' in cd:
            if cd['password'] != cd['password2']:
                raise forms.ValidationError('Passwords don\'t match.')
        return cd['password2']

    def clean_email(self):
        data = self.cleaned_data.get('email')
        if User.objects.filter(email=data).exists():
            raise forms.ValidationError('Email already in use.')
        return data

class LoginForm(forms.Form):
    identifier = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )

# --- New Form for Target Enrollment ---
class TargetPersonForm(forms.ModelForm):
    class Meta:
        model = TargetPerson
        # These fields match your Model exactly
        fields = [
            'name', 'last_name', 'father_name', 'image',
            'age', 'gender', 'place_of_birth', 'marital_status', 'job',
            'tazkira_number', 'phone_number', 'address',
            'crime', 'description'
        ]
        
        # We define widgets to ensure the styling matches your "Cyber" theme
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Surname'}),
            'father_name': forms.TextInput(attrs={'placeholder': 'Father\'s Name'}),
            'tazkira_number': forms.TextInput(attrs={'placeholder': 'ID Number'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '07x xxxx xxx'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Current Residence'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Detailed case notes...'}),
            'age': forms.NumberInput(attrs={'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This loop automatically adds your CSS class to every field
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'cyber-input'})