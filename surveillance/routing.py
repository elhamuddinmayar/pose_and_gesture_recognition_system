from django.urls import re_path
from . import consumers


#websock connetion routing 
websocket_urlpatterns = [
    re_path(r'ws/pose/$', consumers.PoseConsumer.as_asgi()),
]