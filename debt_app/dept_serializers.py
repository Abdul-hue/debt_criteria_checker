from django.contrib.auth.models import User
from rest_framework import serializers

from debt_app.models import (
    Department,
    UserProfile,
    DepartmentRuleVisibility,
    DepartmentCreditorVisibility,
    DepartmentCouncilVisibility,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class _UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class _DepartmentNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']


class UserProfileSerializer(serializers.ModelSerializer):
    user = _UserNestedSerializer(read_only=True)
    department = _DepartmentNestedSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'department']


class DepartmentRuleVisibilitySerializer(serializers.ModelSerializer):
    department = _DepartmentNestedSerializer(read_only=True)
    rule_key = serializers.SerializerMethodField()
    rule_name = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentRuleVisibility
        fields = ['department', 'rule_key', 'rule_name', 'is_visible']

    def get_rule_key(self, obj):
        # rule_key_id holds the string key because the FK uses to_field='rule_key'
        return obj.rule_key_id

    def get_rule_name(self, obj):
        # obj.rule_key is the related GlobalCriteria instance
        return obj.rule_key.rule_name


class DepartmentCreditorVisibilitySerializer(serializers.ModelSerializer):
    department = _DepartmentNestedSerializer(read_only=True)
    creditor = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentCreditorVisibility
        fields = ['department', 'creditor', 'is_visible']

    def get_creditor(self, obj):
        return {'id': obj.creditor_id, 'name': obj.creditor.creditor_name}


class DepartmentCouncilVisibilitySerializer(serializers.ModelSerializer):
    department = _DepartmentNestedSerializer(read_only=True)
    council = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentCouncilVisibility
        fields = ['department', 'council', 'is_visible']

    def get_council(self, obj):
        return {'id': obj.council_id, 'name': obj.council.council_name}
