# Static File Proxy

This is a very simple HTTP proxy for static files.  You can place it in front
of a remote HTTP server and it will download files from that server and cache
them locally.  As long as it remains cached locally, it will not try to pull
a file from the remote server again.

DISCLAIMER:  This is test software.  It needs some love and refactoring. You should probably not use it.
