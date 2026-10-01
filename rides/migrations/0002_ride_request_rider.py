from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_legacy_rides(apps, schema_editor):
    RideRequest = apps.get_model("rides", "RideRequest")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    if RideRequest.objects.filter(rider__isnull=True).exists():
        if User.objects.filter(username="legacy-ride-owner").exists():
            raise RuntimeError(
                "Cannot assign existing rides: username 'legacy-ride-owner' is already in use."
            )
        legacy_user = User.objects.create(
            username="legacy-ride-owner",
            password="!",
            is_active=False,
        )
        RideRequest.objects.filter(rider__isnull=True).update(rider=legacy_user)


def unassign_legacy_rides(apps, schema_editor):
    RideRequest = apps.get_model("rides", "RideRequest")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    legacy_user = User.objects.filter(username="legacy-ride-owner").first()
    if legacy_user is not None:
        RideRequest.objects.filter(rider=legacy_user).update(rider=None)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rides", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="riderequest",
            name="rider",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ride_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_legacy_rides, unassign_legacy_rides),
        migrations.AlterField(
            model_name="riderequest",
            name="rider",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ride_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
