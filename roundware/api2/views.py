# Roundware Server is released under the GNU Affero General Public License v3.
# See COPYRIGHT.txt, AUTHORS.txt, and LICENSE.txt in the project root directory.

# The Django REST Framework Views for the V2 API.
from __future__ import unicode_literals
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from roundware.rw.models import (Asset, Event, ListeningHistoryItem, Project,
                                 Session, Tag, UserProfile, Envelope)
from roundware.api2 import serializers
from roundware.api2.permissions import AuthenticatedReadAdminWrite
from roundware.lib.api import (get_project_tags, modify_stream, move_listener, heartbeat,
                               skip_ahead, add_asset_to_envelope, get_current_streaming_asset)
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, DjangoObjectPermissions
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from rest_framework.authtoken.models import Token
from rest_framework.decorators import detail_route, list_route
import logging

logger = logging.getLogger(__name__)

# TODO: http://www.django-rest-framework.org/api-guide/relations#hyperlinkedrelatedfield

# Note: Keep this stuff in alphabetical order!


# class AssetViewSet(viewsets.ModelViewSet):
#     """
#     API V2: api/2/assets/:asset_id

#     <Permissions>
#     Anonymous: None.
#     Authenticated: GET/POST. PUT/PATCH/DELETE for objects owned by user.
#     Admin: GET/POST/PUT/PATCH/DELETE.
#     """

#     # TODO: Implement DjangoObjectPermissions
#     queryset = Asset.objects.all()
#     serializer_class = serializers.AssetSerializer
#     permission_classes = (IsAuthenticated, DjangoObjectPermissions)


# class EventViewSet(viewsets.ModelViewSet):
#     """
#     API V2: api/2/events/:event_id

#     <Permissions>
#     Anonymous: None.
#     Authenticated: GET/POST
#     Admin: GET/POST
#     """

#     # TODO: Implement ViewCreate permission.
#     queryset = Event.objects.all()
#     serializer_class = serializers.EventSerializer
#     permission_classes = (IsAuthenticated,)


# class ListenEventViewSet(viewsets.ModelViewSet):
#     """
#     API V2: api/2/listenevents/:listenevent_id

#     <Permissions>
#     Anonymous: None.
#     Authenticated: GET/POST.
#     Admin: GET/POST.
#     """

#     # TODO: Implement ViewCreate permission.
#     # TODO: Rename ListeningHistoryItem model to ListenEvent.
#     queryset = ListeningHistoryItem.objects.all()
#     serializer_class = serializers.ListenEventSerializer
#     permission_classes = (IsAuthenticated,)

class EnvelopeViewSet(viewsets.ViewSet):
    """
    API V2: api/2/users/:user_id

    <Permissions>
    Anonymous: POST
    Authenticated: None
    Admin: None
    """
    queryset = Envelope.objects.all()

    def create(self, request):
        """
        POST api/2/envelopes/ - Creates a new envelope based on passed session_id
        """
        serializer = serializers.EnvelopeSerializer(data=request.data)
        if serializer.is_valid():
            envelope = serializer.save()
            return Response({"envelope_id": envelope.pk})
        else:
            return Response(serializer.errors)

    def partial_update(self, request, pk=None):
        """
        PATCH api/2/envelopes/:id/ - Adds an asset to the envelope
        """
        if "asset_id" in request.data or "file" in request.FILES:
            try:
                result = add_asset_to_envelope(request, envelope_id=pk)
            except Exception as e:
                return Response({"detail": str(e)}, status.HTTP_400_BAD_REQUEST)
            return Response({"asset_id": result["asset_id"]})
        else:
            raise ParseError("asset_id required")


class ProjectViewSet(viewsets.ViewSet):
    """
    API V2:

    api/2/projects/:project_id
    <Permissions>
    Anonymous: None
    Authenticated: GET
    Admin: None

    api/2/projects/:project_id/tags
    <Permissions>
    Anonymous: None
    Authenticated: GET
    Admin: None
    """
    queryset = Project.objects.all()
    permission_classes = (IsAuthenticated, )

    def retrieve(self, request, pk=None):
        if "session_id" in request.query_params:
            session = get_object_or_404(Session, pk=request.query_params["session_id"])
            project = get_object_or_404(Project, pk=pk)
            serializer = serializers.ProjectSerializer(project,
                                                       context={"session": session})
        else:
            raise ParseError("session_id is required")
        return Response(serializer.data)

    @detail_route(methods=['get'])
    def tags(self, request, pk=None):
        if "session_id" in request.query_params:
            session = get_object_or_404(Session, pk=request.query_params["session_id"])
            tags = get_project_tags(s=session)
        else:
            raise ParseError("session_id is required")
            project = get_object_or_404(Project, pk=pk)
            tags = get_project_tags(p=project)
        return Response(tags)


class SessionViewSet(viewsets.ViewSet):
    """
    API V2: api/2/sessions/:session_id

    <Permissions>
    Anonymous: None
    Authenticated: GET/POST/PUT/PATCH for objects owned by user.
    Admin: None
    """
    queryset = Session.objects.all()
    permission_classes = (IsAuthenticated, )

    def create(self, request):
        serializer = serializers.SessionSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StreamViewSet(viewsets.ViewSet):
    """
    The primary communication channel for handling the Roundware audio stream.
    Only one stream per user id/token so the end point is not plural.
    API V2: api/2/streams/

    <Permissions>
    Anonymous: None
    Authenticated: POST for the user specific stream.
    Admin: None
    """
    permission_classes = (IsAuthenticated,)

    def create(self, request):
        serializer = serializers.StreamSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            raise ParseError(serializer.errors)
        return Response(serializer.save())

    def partial_update(self, request, pk=None):
        try:
            if "tags" in request.data:
                success = modify_stream(request, context={"pk": pk})
            elif "longitude" in request.data and "latitude" in request.data:
                success = move_listener(request, context={"pk": pk})
            else:
                return ParseError("must supply something to update")
            if success["success"]:
                return Response()
            else:
                return Response({"detail": success["error"]},
                                status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": "could not update stream: %s" % e},
                            status.HTTP_400_BAD_REQUEST)

    @detail_route(methods=['post'])
    def heartbeat(self, request, pk=None):
        try:
            heartbeat(request, session_id=pk)
            return Response()
        except Exception as e:
            return Response({"detail": str(e)},
                            status.HTTP_400_BAD_REQUEST)

    @detail_route(methods=['post'])
    def next(self, request, pk=None):
        try:
            skip_ahead(request, session_id=pk)
            return Response()
        except Exception as e:
            return Response({"detail": str(e)},
                            status.HTTP_400_BAD_REQUEST)

    @detail_route(methods=['get'])
    def current(self, request, pk=None):
        try:
            result = get_current_streaming_asset(request, session_id=pk)
            return Response(result)
        except Exception as e:
            return Response({"detail": str(e)},
                            status.HTTP_400_BAD_REQUEST)

# class TagViewSet(viewsets.ModelViewSet):
#     """
#     API V2: api/2/tags/:tag_id

#     <Permissions>
#     Anonymous: None.
#     Authenticated: GET.
#     Admin: GET/POST/PUT/PATCH/DELETE.
#     """
#     # TODO: Return messages and relationships in response
#     queryset = Tag.objects.all()
#     serializer_class = serializers.TagSerializer
#     permission_classes = (IsAuthenticated, AuthenticatedReadAdminWrite)


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


