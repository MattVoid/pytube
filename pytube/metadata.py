"""This module contains the YouTubeMetadata class."""
import json
from typing import Dict, Optional

class YouTubeMetadata:
    def __init__(self, metadata: dict):
        self._raw_metadata = metadata
        self._metadata = {}

        self.__parse_metadata(metadata)

    def __parse_metadata(self, metadata: dict):
        """Parse the metadata into a list of dicts."""

        actions = metadata.get('actions', [])

        for action in actions:
            
            if "updateViewershipAction" in action:
                self._metadata['viewCount'] = action['updateViewershipAction']['viewCount']['videoViewCountRenderer']['originalViewCount']

            if "updateTitleAction" in action:
                self._metadata['title'] = action['updateTitleAction']['title']['runs'][0]['text']

            if "updateDateAction" in action:
                self._metadata['relativeDate'] = action['updateDateAction']['dateText']['simpleText']

            if "updateDescriptionAction" in action:
                self._metadata['description'] = "".join(list(map(lambda run: run["text"], action['updateDescriptionAction']['description']['runs'])))

    def __getitem__(self, key):
        return self._metadata[key]

    def __str__(self):
        return json.dumps(self._metadata)

    @property
    def raw_metadata(self) -> Optional[Dict]:
        return self._raw_metadata

    @property
    def metadata(self):
        return self._metadata
    
    def get(self, key, default = None):
        return self._metadata.get(key, default)