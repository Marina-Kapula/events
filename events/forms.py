from datetime import datetime

from django import forms
from django.utils import timezone

from config.photos import PhotoField
from events.models import Event, Participation, Size


class EventForm(forms.ModelForm[Event]):
    photo = PhotoField()
    # The browser's own date and time picker. It sends, and needs, this format.
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        )
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "type",
            "description",
            "photo",
            "city",
            "place",
            "starts_at",
            "max_people",
            "language",
        )

    def clean_starts_at(self) -> datetime:
        starts_at: datetime = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("Pick a date and time in the future.")
        return starts_at

    def clean_max_people(self) -> int:
        max_people: int = self.cleaned_data["max_people"]
        if self.instance.pk is None:  # a new event: nobody is going yet
            return max_people
        going = Participation.objects.filter(
            event=self.instance, status=Participation.Status.GOING
        ).count()
        if max_people < 1 + going:
            raise forms.ValidationError(
                f"{going} people are going, so you need at least {1 + going} spots "
                "(you count too)."
            )
        return max_people


class EventFilterForm(forms.Form):
    """The filters above the event list, sent with GET (SPEC §2 #29)."""

    q = forms.CharField(label="Keyword", required=False)
    city = forms.CharField(required=False)
    date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    type = forms.ChoiceField(
        choices=[("", "Any type"), *Event.Type.choices], required=False
    )
    size = forms.ChoiceField(choices=[("", "Any size"), *Size.choices], required=False)
