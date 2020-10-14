# 1.2

* Video playback is back.
* Fixed issue making it crash in Android because it doesn't provide a `/tmp` dir.
* Fix first item in the playlist having a blank name.
* Updated youtube-dl to fix playback issues.
* Remove support for HLS AES from youtube-dl which is not required and pulls in new dependencies.

# 1.1.1

* Removed ability to play video to make the plugin work again.
* Fix out-of-bounds crash when trying to access download URLs for a song that was not found.
* Fix errors with non-ASCII characters in song names.
* Fix for Last.fm providing improperly encoded URLs when they contain a `/` or `&`.
* Updated youtube-dl to fix playback issues.

# 1.1.0

* Replace use of Kodi's plugin.video.youtube to get YouTube download URLs and use youtube-dl instead which gives best results.

# 1.0.0

* First release.
