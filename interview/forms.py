from django import forms

from .models import InterviewSession


class InterviewSetupForm(forms.ModelForm):
    class Meta:
        model = InterviewSession
        fields = [
            "friend_name",
            "target_role",
            "experience_level",
            "skills",
            "resume",
            "job_description",
        ]
        widgets = {
            "friend_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Alex"}),
            "target_role": forms.TextInput(attrs={"class": "form-control", "placeholder": "Backend Engineer"}),
            "experience_level": forms.TextInput(attrs={"class": "form-control", "placeholder": "2 years"}),
            "skills": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Python, Django, SQL"}),
            "resume": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Brief resume summary..."}),
            "job_description": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Describe the role and requirements..."}),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in [
            "friend_name",
            "target_role",
            "experience_level",
            "skills",
            "resume",
            "job_description",
        ]:
            value = cleaned_data.get(field_name)
            if value is not None:
                cleaned_data[field_name] = value.strip()
        return cleaned_data
