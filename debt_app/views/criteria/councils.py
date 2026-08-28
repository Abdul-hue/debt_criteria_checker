"""District council rules and county council routing."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import CouncilRule
from debt_app.helpers import filter_by_department
from debt_app.permissions import HasWritePermission
from debt_app.permissions import HasReadPermission
from debt_app.models import DepartmentCouncilVisibility
from debt_app.models import CountyCouncil

def _council_to_dict(c):
    return {
        "id": c.id,
        "council_name": c.council_name,
        "status": c.status,
        "min_dividend_pence": c.min_dividend_pence,
        "do_not_chase": c.do_not_chase,
        "include_current_year_ct": c.include_current_year_ct,
        "reject_if_employed": c.reject_if_employed,
        "reject_if_unemployed_and_homeowner": c.reject_if_unemployed_and_homeowner,
        "reject_if_benefits_only": c.reject_if_benefits_only,
        "reject_if_any_benefits": c.reject_if_any_benefits,
        "reject_if_previous_iva": c.reject_if_previous_iva,
        "reject_if_dro_criteria_met": c.reject_if_dro_criteria_met,
        "reject_if_aoe_in_place": c.reject_if_aoe_in_place,
        "reject_if_joint_one_party_only": c.reject_if_joint_one_party_only,
        "reject_if_joint_both_parties": c.reject_if_joint_both_parties,
        "reject_if_joint_one_employed": c.reject_if_joint_one_employed,
        "reject_if_sole": c.reject_if_sole,
        "blocked_reason": c.blocked_reason,
        "criteria_changed_from_rej_date": c.criteria_changed_from_rej_date,
        "contact_name": c.contact_name,
        "contact_number": c.contact_number,
        "source_priority": c.source_priority,
        "last_reviewed": c.last_reviewed.isoformat() if c.last_reviewed else None,
    }


_COUNCIL_WRITABLE_FIELDS = [
    'council_name', 'status', 'min_dividend_pence', 'do_not_chase',
    'include_current_year_ct', 'reject_if_employed', 'reject_if_unemployed_and_homeowner',
    'reject_if_benefits_only', 'reject_if_any_benefits', 'reject_if_previous_iva',
    'reject_if_dro_criteria_met', 'reject_if_aoe_in_place', 'reject_if_joint_one_party_only',
    'reject_if_joint_both_parties', 'reject_if_sole', 'reject_if_joint_one_employed',
    'blocked_reason', 'criteria_changed_from_rej_date', 'contact_name', 'contact_number',
    'source_priority', 'last_reviewed',
]


class CouncilRuleListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = CouncilRule.objects.all().order_by('council_name')
        if search:
            queryset = queryset.filter(council_name__icontains=search)

        queryset = filter_by_department(
            queryset, CouncilRule, request.user,
            DepartmentCouncilVisibility, 'council',
        )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_council_to_dict(c) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('council_name'):
            return Response({"detail": "council_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CouncilRule.objects.filter(council_name=data['council_name']).exists():
            return Response({"detail": "A council with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        council = CouncilRule()
        for field in _COUNCIL_WRITABLE_FIELDS:
            if field in data:
                setattr(council, field, data[field])

        try:
            council.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        council.save()
        return Response(_council_to_dict(council), status=status.HTTP_201_CREATED)


class CouncilRuleDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return CouncilRule.objects.get(id=pk)
        except CouncilRule.DoesNotExist:
            return None

    def get(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_council_to_dict(council), status=status.HTTP_200_OK)

    def put(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _COUNCIL_WRITABLE_FIELDS:
            if field in request.data:
                setattr(council, field, request.data[field])

        try:
            council.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        council.save()
        return Response(_council_to_dict(council), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        council.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _county_council_to_dict(c, include_districts=False):
    data = {
        "id": c.id,
        "county_name": c.county_name,
        "status": c.status,
        "deals_with_council_tax": c.deals_with_council_tax,
        "min_dividend_pence": c.min_dividend_pence,
        "blocked_reason": c.blocked_reason,
        "contact_name": c.contact_name,
        "contact_number": c.contact_number,
        "last_reviewed": c.last_reviewed.isoformat() if c.last_reviewed else None,
    }
    if include_districts:
        districts = [
            {
                "id": d.id,
                "district_name": d.district_name,
                "council_rule_id": d.council_rule_id,
                "council_rule_name": d.council_rule.council_name if d.council_rule_id else None,
                "council_rule_status": d.council_rule.status if d.council_rule_id else None,
            }
            for d in sorted(c.districts.all(), key=lambda d: d.district_name)
        ]
        data["districts"] = districts
        data["district_count"] = len(districts)
    else:
        data["district_count"] = c.districts.count()
    return data


_COUNTY_COUNCIL_WRITABLE_FIELDS = [
    'county_name', 'status', 'deals_with_council_tax', 'min_dividend_pence',
    'blocked_reason', 'contact_name', 'contact_number', 'last_reviewed',
]


class CountyCouncilListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = CountyCouncil.objects.all().order_by('county_name').prefetch_related(
            'districts', 'districts__council_rule',
        )
        if search:
            queryset = queryset.filter(county_name__icontains=search)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_county_council_to_dict(c, include_districts=True) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('county_name'):
            return Response({"detail": "county_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CountyCouncil.objects.filter(county_name=data['county_name']).exists():
            return Response({"detail": "A county council with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        county = CountyCouncil()
        for field in _COUNTY_COUNCIL_WRITABLE_FIELDS:
            if field in data:
                setattr(county, field, data[field])

        try:
            county.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        county.save()
        return Response(_county_council_to_dict(county), status=status.HTTP_201_CREATED)


class CountyCouncilDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return CountyCouncil.objects.get(id=pk)
        except CountyCouncil.DoesNotExist:
            return None

    def get(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_county_council_to_dict(county, include_districts=True), status=status.HTTP_200_OK)

    def put(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _COUNTY_COUNCIL_WRITABLE_FIELDS:
            if field in request.data:
                setattr(county, field, request.data[field])

        try:
            county.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        county.save()
        return Response(_county_council_to_dict(county, include_districts=True), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        county.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
