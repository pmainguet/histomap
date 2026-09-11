# HYDE population, aggregated by civilization entity

- Source: sources\hyde\population.nc (HYDE 3.4, Klein Goldewijk & Beusen), coarsened 12x to a 1-degree grid, classified by ISO2 country code using the same point-in-polygon boundaries as extract_hyde_by_continent.py (sources\ne_110m_admin_0_countries.geojson).
- 28 eligible entities considered (entity_type in ['archaeological_horizon', 'civilization', 'culture', 'people', 'tribe'], eligibility accepted, present_countries set).
- 27 entities got a population time series.
- 1 entities matched cells but had no HYDE sample year inside their [start, end]: ancient_carthage.
- 280 (entity, year) rows written to sources\hyde_population_by_civilization.json, one row per HYDE sample year within each entity's own [start, end] (end: null means every HYDE year from start onward).

Known limitation: this masks by *modern* country borders, not a historical territorial boundary -- it counts the *entire* HYDE population of every present_countries country during the entity's active years, a systematic overcount for any entity that only occupied part of a large modern country (e.g. the Maya heartland is a fraction of Mexico's territory, but this counts all of Mexico's HYDE population). Useful as a *relative* width signal for pipeline/poster.py's population-driven band width -- which years look bigger than others for the *same* entity -- not a headcount or a reliable cross-entity comparison.

Rerun this script whenever sources/hyde/population.nc is refreshed, or when a civilization-type entity's present_countries/start/end changes -- build.py itself only copies this cached file through, it never recomputes it.
