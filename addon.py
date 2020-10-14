import sys
import xbmcgui
import xbmcplugin
import xbmcaddon

import urllib, urllib2, urlparse
import string, base64, json
import os.path, tempfile

# Try to import bundled youtube-dl library first and failback to system one
sys.path.insert(0, os.path.join(xbmcaddon.Addon().getAddonInfo('path'), "resources", "lib", "youtube-dl"))

# Needed classes from youtube-dl
from youtube_dl import YoutubeDL
from youtube_dl.utils import DownloadError

# Just a reminder:
# argv:
# 0: base URL
# 1: handle
# 3: query string

# Know a little about myself:
addon_name = xbmcaddon.Addon().getAddonInfo("name")
addon_handle = int(sys.argv[1])
base_url = sys.argv[0]
args = urlparse.parse_qs(sys.argv[2][1:])

# Prepend module name to error messages
def log(msg, level=xbmc.LOGINFO):
    xbmc.log(msg="[%s] %s" % (addon_name, msg), level=level)

def want_video():
    return ("content_type" in args and "video" in args["content_type"]) or ("video" in args and "True" in args["video"])

# Method to show main menu
def main_menu():
    lastfm_user = xbmcaddon.Addon().getSetting("username")
    if not lastfm_user:
        xbmcgui.Dialog().ok("Not configured", "Please configure first")
    else:
        xbmcplugin.setContent(addon_handle, 'music{}'.format('videos' if want_video() else ''))
        """ Was neighbours station shut down? Or is it only one of the
        services not working after Last.fm rolled out their beta and
        everything is broken until it comes back "soon"? """
        for station in ["library", "mix", "recommended"]:
            li = xbmcgui.ListItem('Last.fm %s %s' % (lastfm_user, station), iconImage='DefaultMusicPlaylists.png')
            li.setInfo("video" if want_video() else "music", {})
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.addDirectoryItem(handle=addon_handle, url="{}?station=user/{}/{}&video={}".format(base_url, lastfm_user, station, want_video()), listitem=li)
        xbmcplugin.endOfDirectory(addon_handle)

""" Last.fm servers seemed to be pretty unstable when their beta website was
 rolled out and they reply with errors quite often.
 Now they seem more stable, but we keep the option to ask user if it wants
 to retry when servers reply with an error"""
def lastfm_error_retry(msg):
    log(msg=msg, level=xbmc.LOGWARNING)
    return xbmcgui.Dialog().yesno("Last.fm error", msg, "Last.fm servers seem to fail randomly sometimes", "Do you want to try again?")

""" Last.fm returns track artist as an array of artists.
This function converts that array to a comma-separated string for music items
or an array of strings for videos"""
def artists_array(artists_array):
    artists = [artists_array[0]["name"]] if want_video() else artists_array[0]["name"]
    if want_video():
        for i in range(1, len(artists_array)):
            artists.append(artists_array[i]["name"])
    else:
        for i in range(1, len(artists_array)):
            artists += ", " + artists_array[i]["name"]
    return artists

# Get next track from given station
def get_next_track(station):
    """ Playlists and current position in playlist is stored in
    temporary files with encoded station URL"""
    encoded_station = base64.urlsafe_b64encode(station)
    try:
        tempdir = tempfile.gettempdir()
    except IOError:
        # FIXME there is probably a better way to do this
        # maybe replace the whole file handling with xbmcvfs?
        if xbmc.getCondVisibility('system.platform.android'):
            tempdir = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp"
    json_playlist = os.path.join(tempdir, "kodi-lastfm_%s.json" % encoded_station)
    playlist_position = os.path.join(tempdir, "kodi-lastfm_%s.pos" % encoded_station)

    """ Will be set to True if playlist is empty or we already are
    at the end, so a new playlist for this station has to be downloaded"""
    force_download = False

    if not os.path.isfile(json_playlist):
        # Playlist was not downloaded yet
        force_download = True
    else:
        with open(json_playlist, "r") as f:
            tracklist = json.loads(f.read())
            f.close()
        with open(playlist_position, "r") as f:
            try:
                next_pos = int(f.read())
            except ValueError:
                # We can't get current track, start from the beginning
                next_pos = 0
            if next_pos >= len(tracklist["playlist"]):
                # We are at the end of the playlist
                force_download = True
            f.close()
        if not force_download:
            # Save new position
            with open(playlist_position, "w") as f:
                f.write(str(next_pos+1))
                f.close()

    if force_download:
        log(msg="Downloading next page of station %s playlist" % station, level=xbmc.LOGINFO)
        """ Retry loop executed until we get a succesful reply from
        Last.fm server (they used to fail a lot when they rolled out
        their beta) or user aborts."""
        while True:
            try:
                response = urllib2.urlopen("https://www.last.fm/player/station/%s" % station)
            except urllib2.HTTPError:
                if lastfm_error_retry("Last.fm servers replied with error status."):
                    continue
                else:
                    return None

            # Get and decode response
            json_tracklist = response.read()

            """ Save playlist in a file so we can access it again
            to fetch next track when a new track is going to be played """
            with open(json_playlist, "w") as f:
                f.write(json_tracklist)
                f.close()
            """ Save current position in Last.fm playlist so we can later
            know which one is next """
            with open(playlist_position, "w") as f:
                f.write("1")
                f.close()

            tracklist = json.loads(json_tracklist)

            # Validate tracklist
            if not "playlist" in tracklist:
                if lastfm_error_retry("No playlist received from Last.fm"):
                    continue
                else:
                    return None
            if len(tracklist["playlist"]) == 0:
                if lastfm_error_retry("Empty playlis received from Last.fm"):
                    continue
                else:
                    return None

            # No errors, break retry loop
            next_pos = 0
            break

    return tracklist["playlist"][next_pos]

""" We were requested to resolve an iternal URL like
plugin://plugin.video.lastfm/?track=/music/Bachman-Turner+Overdrive/_/You+Ain%27t+Seen+Nothing+Yet
to something playable by Kodi, i.e. a download link for a YouTube video like
https://r5---sn-h5q7dne6.googlevideo.com/videoplayback?id=...
"""
if "track" in args:
    log(msg="Resolving track %s" % args["track"][0], level=xbmc.LOGDEBUG)

    next_track = None
    station_arg = ""
    """ We should have received the station this song belongs to so
    we can know which one goes next... But we have to be prepared for
    the unexpected... """
    if "station" in args:
        next_track = get_next_track(args["station"][0])
        station_arg = "&station=%s" % args["station"][0]
        if not next_track:
            log(msg="Unable to get next track for station %s" % args["station"][0], level=xbmc.LOGWARNING)
    else:
        log(msg="Received track without the station it belongs to. Dynamic playlist disabled.", level=xbmc.LOGNOTICE)

    """ As we prepare to resolve current track, we queue next
    track to playlist """
    if next_track:
        log(msg="Queueing track %s" % next_track["url"], level=xbmc.LOGDEBUG)
        artists = artists_array(next_track["artists"])
        li = xbmcgui.ListItem(" - ".join([", ".join(artists) if want_video() else artists, next_track["name"]]))
        li.setInfo("video" if want_video() else "music", {'artist': artists, 'title': next_track["name"]})
        li.setProperty('IsPlayable', 'true')
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.add(url="{}?track={}&station={}&video={}".format(base_url, next_track["url"].replace("&", "%26"), station_arg, want_video()), listitem=li, index=playlist.size())

    """ Now, here we go with the stuff we were requested: resolving
    to a playable URL """

    """ TODO: for now, we are discarding YouTube links provided by
    Last.fm because they contain crap too many times. Make this
    optional """
    (_, _, artist, _, title) = string.split(args["track"][0], "/", 4)
    artist = urllib.unquote_plus(artist)
    title = urllib.unquote_plus(title)
    log(msg="Searching track %s" % " - ".join([artist, title]), level=xbmc.LOGDEBUG)

    try:
        ydl_opts = {
            'format': 'best{}'.format('' if want_video() else 'audio'),
            'no_color': True
        }
        ydl = YoutubeDL(ydl_opts)
        # TODO: Use more video providers than YouTube
        playback_url = ydl.extract_info("ytsearch: %s" % " - ".join([artist.decode("utf-8"), title.decode("utf-8")]), download=False)
        if len(playback_url["entries"]) == 0:
            raise DownloadError("Song not found")
        li = xbmcgui.ListItem(path=playback_url["entries"][0]["url"])
        li.setInfo("video" if want_video() else "music", {'artist': [artist], 'title': title})
        xbmcplugin.setResolvedUrl(addon_handle, True, li)
    except DownloadError:
        xbmcgui.Dialog().ok("Song not found", ' - '.join([artist, title]))

elif "station" in args:
    log(msg="Starting station %s" % args["station"][0], level=xbmc.LOGINFO)

    track = get_next_track(args["station"][0])

    if track:
        # We first remove all other items from the playlist so we can do our magic
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        # but we save a reference to our starting list item to add it later
        current_li = playlist[playlist.getposition()]
        playlist.clear()

        artists = artists_array(track["artists"])
        li = xbmcgui.ListItem(path="{}?track={}&station={}&video={}".format(base_url, track["url"], args["station"][0], want_video()))
        li.setInfo("video" if want_video() else "music", {'artist': artists, 'title': track["name"]})
        li.setProperty('IsPlayable', 'true')

        """We need to add back to the playlist our starting item with a reference to the station
        (well, it doesn't really matter what the first item is) and also the first song from the
        station we are going to play now.
        Without this, it would stop playing after the first song."""
        current_li.setInfo("video" if want_video() else "music", {})
        playlist.add(url="%s?%s" % (base_url, sys.argv[2][1:]), listitem=current_li, index=0)
        playlist.add(url="{}?track={}&station={}&video={}".format(base_url, track["url"], args["station"][0], want_video()), listitem=li, index=1)

        xbmcplugin.setResolvedUrl(addon_handle, True, li)

    else:
        log(msg="Couldn't start station %s" % args["station"][0], level=xbmc.LOGERROR)
        main_menu()

else:
    main_menu()
