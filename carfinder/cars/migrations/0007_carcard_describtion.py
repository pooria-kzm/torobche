from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cars", "0006_alter_car_type_nullable")]
    operations = [migrations.AddField(
        model_name="carcard", name="describtion", field=models.TextField(blank=True),
    )]
