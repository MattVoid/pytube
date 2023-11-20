"""Module for interacting with YouTube search."""
# Native python imports
import logging
from enum import Enum

# Local imports
from pytube import YouTube, Channel
from pytube.innertube import InnerTube


logger = logging.getLogger(__name__)

class Params(Enum):
    FILTER_CHANNEL = 'EgIQAg%3D%3D'
    FILTER_PLAYLIST = 'EgIQAw%3D%3D'
    FILTER_VIDEO = 'EgIQAQ%3D%3D'
    FILTER_MOVIE = 'EgIQBA%3D%3D'


class Search:
    def __init__(self, query: str, param: Params|None = None):
        """Initialize Search object.

        :param str query:
            Search query provided by the user.
        """
        self.query = query
        self.param = param
        self._innertube_client = InnerTube(client='WEB')

        # The first search, without a continuation, is structured differently
        #  and contains completion suggestions, so we must store this separately
        self._initial_results = None

        self._results = None
        self._completion_suggestions = None

        # Used for keeping track of query continuations so that new results
        #  are always returned when get_next_results() is called
        self._current_continuation = None

    @property
    def completion_suggestions(self):
        """Return query autocompletion suggestions for the query.

        :rtype: list
        :returns:
            A list of autocomplete suggestions provided by YouTube for the query.
        """
        if self._completion_suggestions:
            return self._completion_suggestions
        if self.results:
            self._completion_suggestions = self._initial_results['refinements']
        return self._completion_suggestions

    @property
    def results(self):
        """Return search results.

        On first call, will generate and return the first set of results.
        Additional results can be generated using ``.get_next_results()``.

        :rtype: list
        :returns:
            A list of YouTube objects.
        """
        if self._results:
            return self._results

        videos, continuation = self.fetch_and_parse()
        self._results = videos
        self._current_continuation = continuation
        return self._results

    def get_next_results(self):
        """Use the stored continuation string to fetch the next set of results.

        This method does not return the results, but instead updates the results property.
        """
        if self._current_continuation:
            videos, continuation = self.fetch_and_parse(self._current_continuation)
            self._results.extend(videos)
            self._current_continuation = continuation
        else:
            raise IndexError

    def _parse_video(self, video_details):
        # Extract relevant video information from the details.
        # Some of this can be used to pre-populate attributes of the
        #  YouTube object.
        renderer = video_details['videoRenderer']
        id = renderer['videoId']
        url = f'https://www.youtube.com/watch?v={id}'
        title = renderer['title']['runs'][0]['text']
        channel_name = renderer['ownerText']['runs'][0]['text']
        channel_uri = renderer['ownerText']['runs'][0]['navigationEndpoint']['commandMetadata']['webCommandMetadata']['url']
        # Livestreams have "runs", non-livestreams have "simpleText",
        #  and scheduled releases do not have 'viewCountText'
        if 'viewCountText' in renderer:
            if 'runs' in renderer['viewCountText']:
                view_count_text = renderer['viewCountText']['runs'][0]['text']
            else:
                view_count_text = renderer['viewCountText']['simpleText']
            # Strip ' views' text, then remove commas
            stripped_text = view_count_text.split()[0].replace(',','')
            if stripped_text == 'No':
                view_count = 0
            else:
                view_count = int(stripped_text)
        else:
            view_count = 0

        if 'lengthText' in renderer:
            length = renderer['lengthText']['simpleText']
        else:
            length = None

        metadata = {
            'id': id,
            'url': url,
            'title': title,
            'channel_name': channel_name,
            'channel_url': channel_uri,
            'view_count': view_count,
            'length': length
        }

        # Construct YouTube object from metadata and append to results
        video = YouTube(metadata['url'])
        video.author = metadata['channel_name']
        video.title = metadata['title']

        return video

    def _parse_channel(self, channel_details):
        renderer = channel_details['channelRenderer']
        channel_id = renderer['channelId']
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        return Channel(channel_url)

    def fetch_and_parse(self, continuation=None):
        """Fetch from the innertube API and parse the results.

        :param str continuation:
            Continuation string for fetching results.
        :rtype: tuple
        :returns:
            A tuple of a list of YouTube objects and a continuation string.
        """
        # Begin by executing the query and identifying the relevant sections
        #  of the results
        raw_results = self.fetch_query(continuation)

        # Initial result is handled by try block, continuations by except block
        try:
            sections = raw_results['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
        except KeyError:
            sections = raw_results['onResponseReceivedCommands'][0]['appendContinuationItemsAction']['continuationItems']
        item_renderer = None
        continuation_renderer = None
        for s in sections:
            if 'itemSectionRenderer' in s:
                item_renderer = s['itemSectionRenderer']
            if 'continuationItemRenderer' in s:
                continuation_renderer = s['continuationItemRenderer']

        # If the continuationItemRenderer doesn't exist, assume no further results
        if continuation_renderer:
            next_continuation = continuation_renderer['continuationEndpoint']['continuationCommand']['token']
        else:
            next_continuation = None

        results = None

        # If the itemSectionRenderer doesn't exist, assume no results.
        if item_renderer:

            results = []
            contents = item_renderer['contents']

            for details in contents:

                # Skip over ads
                if details.get('searchPyvRenderer', {}).get('ads', None):
                    continue

                # Skip "recommended" type videos e.g. "people also watched" and "popular X"
                #  that break up the search results
                elif 'shelfRenderer' in details:
                    continue

                # Skip auto-generated "mix" playlist results
                elif 'radioRenderer' in details:
                    continue

                # Skip playlist results
                elif 'playlistRenderer' in details:
                    continue

                # Skip 'people also searched for' results
                elif 'horizontalCardListRenderer' in details:
                    continue

                # Can't seem to reproduce, probably related to typo fix suggestions
                elif 'didYouMeanRenderer' in details:
                    continue

                # Seems to be the renderer used for the image shown on a no results page
                elif 'backgroundPromoRenderer' in details:
                    continue

                # Parse video results
                elif 'videoRenderer' in details:
                    result = self._parse_video(details)

                # Parse channel results
                elif 'channelRenderer' in details:
                    result = self._parse_channel(details)
                
                else:

                    logger.warning('Unexpected renderer encountered.')
                    logger.warning(f'Renderer name: {details.keys()}')
                    logger.warning(f'Search term: {self.query}')
                    logger.warning(
                        'Please open an issue at '
                        'https://github.com/pytube/pytube/issues '
                        'and provide this log output.'
                    )
                    continue

                results.append(result)

        return results, next_continuation

    def fetch_query(self, continuation=None):
        """Fetch raw results from the innertube API.

        :param str continuation:
            Continuation string for fetching results.
        :rtype: dict
        :returns:
            The raw json object returned by the innertube API.
        """
        query_results = self._innertube_client.search(self.query, self.param, continuation)
        if not self._initial_results:
            self._initial_results = query_results
        return query_results  # noqa:R504
