"""Authentication and first-run account setup forms."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model


User = get_user_model()


class OperatorLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(attrs={"autofocus": True, "class": "form-input"}),
    )
    password = forms.CharField(
        label="گذرواژه",
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
    )


class FirstOperatorSetupForm(UserCreationForm):
    """First-run account creation; this form must never be available again."""

    class Meta:
        model = User
        fields = ("username", "password1", "password2")
        labels = {
            "username": "نام کاربری",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={"autofocus": True, "class": "form-input"}
            ),
            "password1": forms.PasswordInput(attrs={"class": "form-input"}),
            "password2": forms.PasswordInput(attrs={"class": "form-input"}),
        }
