# HYDE population, aggregated by continent

- Source: sources\hyde\population.nc (HYDE 3.4, Klein Goldewijk & Beusen), coarsened 12x to a 1-degree grid before continent classification.
- Continent boundaries: sources\ne_110m_admin_0_countries.geojson.
- 6 continents written: africa, asia, europe, north_america, oceania, south_america -- Antarctica and Natural Earth's placeholder "Seven seas (open ocean)" feature are always 0 across every time step and dropped rather than kept as empty rows.
- 66.8% of coarse grid cells are ocean/unclaimed (excluded from every continent's sum, not double-counted or dropped silently).
- 128 time steps, 768 (year, continent) rows written to sources\hyde_population_by_continent.json.
- Known limitation: the latest time step's continent totals sum to ~7.4 billion, roughly 10% under the actual current world population (~8.2 billion) -- the 110m-resolution country boundaries lose some coastal/small-island population at 1-degree coarsening. Good enough for the /explore Population lane's relative continent-shape-over-time visualization; not a substitute for an authoritative modern headcount.

Rerun this script whenever sources/hyde/population.nc is refreshed with a newer HYDE release -- build.py itself only copies this cached file through, it never recomputes it.
