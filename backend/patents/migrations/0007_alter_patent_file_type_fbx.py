from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patents', '0006_patent_glb_file_path'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patent',
            name='file_type',
            field=models.CharField(
                choices=[
                    ('OBJ', 'Wavefront OBJ'),
                    ('STL', 'Stereolithography'),
                    ('STP', 'STEP File'),
                    ('IGES', 'IGES File'),
                    ('GLB', 'GLB File'),
                    ('FBX', 'FBX File'),
                ],
                help_text='Type of the 3D model file',
                max_length=4,
                null=True,
            ),
        ),
    ]