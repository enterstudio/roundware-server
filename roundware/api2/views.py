# Roundware Server is released under the GNU Affero General Public License v3.
# See COPYRIGHT.txt, AUTHORS.txt, and LICENSE.txt in the project root directory.

# The Django REST Framework Views for the V2 API.
from __future__ import unicode_literals
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from roundware.rw.models import (Asset, Event, ListeningHistoryItem, Project,
                                 Session, Tag, UserProfile)
from roundware.api2 import serializers
from roundware.api2.permissions import AuthenticatedReadAdminWrite
from roundware.lib.api import get_project_tags
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, DjangoObjectPermissions
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from rest_framework.authtoken.models import Token
from rest_framework.decorators import detail_route, list_route
import logging

logger = logging.getLogger(__name__)

# TODO: http://www.django-rest-framework.org/api-guide/relations#hyperlinkedrelatedfield

# Note: Keep this stuff in alphabetical order!


class AssetViewSet(viewsets.ModelViewSet):
    """
    API V2: api/2/assets/:asset_id

    <Permissions>
    Anonymous: None.
    Authenticated: GET/POST. PUT/PATCH/DELETE for objects owned by user.
    Admin: GET/POST/PUT/PATCH/DELETE.
    """

    # TODO: Implement DjangoObjectPermissions
    queryset = Asset.objects.all()
    serializer_class = serializers.AssetSerializer
    permission_classes = (IsAuthenticated, DjangoObjectPermissions)


class EventViewSet(viewsets.ModelViewSet):
    """
    API V2: api/2/events/:event_id

    <Permissions>
    Anonymous: None.
    Authenticated: GET/POST
    Admin: GET/POST
    """

    # TODO: Implement ViewCreate permission.
    queryset = Event.objects.all()
    serializer_class = serializers.EventSerializer
    permission_classes = (IsAuthenticated,)


class ListenEventViewSet(viewsets.ModelViewSet):
    """
    API V2: api/2/listenevents/:listenevent_id

    <Permissions>
    Anonymous: None.
    Authenticated: GET/POST.
    Admin: GET/POST.
    """

    # TODO: Implement ViewCreate permission.
    # TODO: Rename ListeningHistoryItem model to ListenEvent.
    queryset = ListeningHistoryItem.objects.all()
    serializer_class = serializers.ListenEventSerializer
    permission_classes = (IsAuthenticated,)


class StreamViewSet(viewsets.ViewSet):
    """
    The primary communication channel for handling the Roundware audio stream.
    Only one stream per user id/token so the end point is not plural.
    API V2: api/2/stream/

    <Permissions>
    Anonymous: None.
    Authenticated: GET/POST/PUT/PATCH for the user specific stream.
    Admin: GET/POST/PUT/PATCH for the user specific stream.
    """
    permission_classes = (IsAuthenticated,)

    def list(self, request):
        """
        GET api/2/stream/ - Gets information about an existing stream
        """
        # Validate the input
        serializer = serializers.StreamSerializer(data=request.GET)
        if not serializer.is_valid():
            raise ParseError(serializer.errors)

        # TODO: Return data about the stream, only if it exists.
        return Response(serializer.data)

    def create(self, request):
        serializer = serializers.StreamSerializer()
        return Response(serializer.data)


class SessionViewSet(viewsets.ModelViewSet):
    """
    API V2: api/2/sessions/:session_id

    <Permissions>
    Anonymous: None.
    Authenticated: GET/POST/PUT/PATCH for objects owned by user.
    Admin: GET/POST/PUT/PATCH.
    """
    queryset = Session.objects.all()
    serializer_class = serializers.SessionSerializer
    permission_classes = (IsAuthenticated, AuthenticatedReadAdminWrite)


class TagViewSet(viewsets.ModelViewSet):
    """
    API V2: api/2/tags/:tag_id

    <Permissions>
    Anonymous: None.
    Authenticated: GET.
    Admin: GET/POST/PUT/PATCH/DELETE.
    """
    # TODO: Return messages and relationships in response
    queryset = Tag.objects.all()
    serializer_class = serializers.TagSerializer
    permission_classes = (IsAuthenticated, AuthenticatedReadAdminWrite)


class UserViewSet(viewsets.ViewSet):
    """
    API V2: api/2/users/:user_id

    <Permissions>
    Anonymous: POST
    Authenticated: None
    Admin: None
    """
    queryset = User.objects.all()

    def create(self, request):
        """
        POST api/2/user/ - Creates new user based on either device_id or username/pass. Returns token
        """
        serializer = serializers.UserSerializer(data=request.data)
        if serializer.is_valid():
            # try to find user profile:
            try:
                profile = UserProfile.objects.get(device_id=self.request.data["device_id"][:254])
                user = profile.user
                # try to find existing token
                try:
                    token = Token.objects.get(user=profile.user)
                # create a token for this profile
                except Token.DoesNotExist:
                    token = Token.objects.create(user=profile.user)
            # no matching device_id in profiles, create new user
            except UserProfile.DoesNotExist:
                # save the serializer to create new user account
                user = serializer.save()
                # obtain token for this new user
                token = Token.objects.create(user=user)
        return Response({"username": user.username, "token": token.key})


class ProjectViewSet(viewsets.ViewSet):
    """
    API V2: api/2/projects/:project_id
            api/2/projects/:project_id/tags

    <Permissions>
    Anonymous: None
    Authenticated: GET
    Admin: None
    """
    queryset = Project.objects.all()
    permission_classes = (IsAuthenticated, )

    def retrieve(self, request, pk=None):
        project = get_object_or_404(Project, pk=pk)
        serializer = serializers.ProjectSerializer(project)
        return Response(serializer.data)

    @detail_route(methods=['get'])
    def tags(self, request, pk=None):
        project = get_object_or_404(Project, pk=pk)
        tags = get_project_tags(p=project)
        return Response(tags)
