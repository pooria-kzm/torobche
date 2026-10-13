from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("cars", "0001_initial")]
    operations = [migrations.AlterField(
        model_name="car", name="source",
        field=models.CharField(choices=[("bama", "باما"), ("karnameh", "کارنامه"), ("hamrah", "همراه مکانیک"), ("khodro45", "خودرو۴۵"), ("divar", "دیوار"), ("sheypoor", "شیپور")], max_length=16),
    )]
