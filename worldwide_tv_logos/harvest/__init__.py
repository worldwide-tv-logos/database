"""Looking for logos in bulk: candidates (candidates.py), duplicates and brands (duplicates.py), contact sheets
(sheets.py), and the jobs (run.py: harvest, hunt, bulk import, guide check). The sources themselves are in
worldwide_tv_logos/sources/."""
from worldwide_tv_logos.harvest.candidates import (
                                                   QUALITY_FEED,
                                                   Candidate,
                                                   evaluate,
                                                   load_epg,
                                                   load_rejected,
                                                   same_as_channel,
                                                   units,
                                                   update_reason,
)
from worldwide_tv_logos.harvest.duplicates import (
                                                   CROSS_TOLERANCE,
                                                   brand,
                                                   brand_differences,
                                                   drawing_of_other,
                                                   family,
                                                   logo_url,
                                                   number,
                                                   repo_drawings,
                                                   same_image,
                                                   set_countries,
                                                   shared_drawings,
                                                   split_duplicates,
)
from worldwide_tv_logos.harvest.run import bulk, epg_check, harvest, summary
from worldwide_tv_logos.harvest.sheets import contact_sheets, render_sheets, repo_sheets
from worldwide_tv_logos.sources.names import channel_keys, key

__all__ = ['CROSS_TOLERANCE', 'QUALITY_FEED', 'Candidate', 'brand', 'brand_differences', 'bulk', 'channel_keys',
           'contact_sheets', 'drawing_of_other', 'epg_check', 'evaluate', 'family', 'harvest', 'key', 'load_epg',
           'load_rejected', 'logo_url', 'number', 'render_sheets', 'repo_drawings', 'repo_sheets', 'same_as_channel',
           'same_image', 'set_countries', 'shared_drawings', 'split_duplicates', 'summary', 'units', 'update_reason']
