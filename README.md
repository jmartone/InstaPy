# InstaPy

A Python wrapper for the Instagram API

### Supported Endpoints and Their Respective Methods
Method | Endpoint
:---|:---
handle_to_id() | [GET users/search](https://www.instagram.com/developer/endpoints/users/)
self_followed_by() | [GET users/self/followed-by](https://www.instagram.com/developer/endpoints/relationships/)
media_recent() | [GET users/{user-id}/media/recent](https://www.instagram.com/developer/endpoints/users/)
media_comments() | [GET media/{media-id}/comments](https://www.instagram.com/developer/endpoints/comments/)
media_likes() | [GET media/{media-id}/likes](https://www.instagram.com/developer/endpoints/likes/)
media() | [GET media/shortcode/{shortcode}](https://www.instagram.com/developer/endpoints/media/)<br>[GET media/{media-id}](https://www.instagram.com/developer/endpoints/media/)
locations_search() | [GET locations/search](https://www.instagram.com/developer/endpoints/locations/)
locations_media_recent() | [GET locations/{location-id}/media/recent](https://www.instagram.com/developer/endpoints/locations/)
locations() | [GET locations/{location-id}](https://www.instagram.com/developer/endpoints/locations/)
tag_media_recent() | [GET tags/{tag}/media/recent](https://www.instagram.com/developer/endpoints/locations/)