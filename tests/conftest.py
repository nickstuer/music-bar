import logging

import music_bar.music_bar  # noqa: F401 - configures the package logger on import

# Keep test runs out of the user's real ~/.music-bar/app.log.
for handler in list(logging.getLogger("music_bar").handlers):
    if isinstance(handler, logging.FileHandler):
        logging.getLogger("music_bar").removeHandler(handler)
        handler.close()
