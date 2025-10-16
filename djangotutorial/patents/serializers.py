from rest_framework import serializers

from patents.models import Patent


class PatentUploadSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Patent
        fields = ['id', 'user', 'patent_file', 'uploaded_at']
        read_only_fields = ['uploaded_at']