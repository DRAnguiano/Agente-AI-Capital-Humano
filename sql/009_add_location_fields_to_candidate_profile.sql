BEGIN;

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS ciudad_raw TEXT,
ADD COLUMN IF NOT EXISTS estado_region TEXT,
ADD COLUMN IF NOT EXISTS pais_codigo TEXT,
ADD COLUMN IF NOT EXISTS pais_nombre TEXT,
ADD COLUMN IF NOT EXISTS city_group TEXT,
ADD COLUMN IF NOT EXISTS is_local_laguna BOOLEAN,
ADD COLUMN IF NOT EXISTS is_foreign_country BOOLEAN,
ADD COLUMN IF NOT EXISTS location_requires_ch_validation BOOLEAN,
ADD COLUMN IF NOT EXISTS location_needs_travel_validation BOOLEAN,
ADD COLUMN IF NOT EXISTS city_catalog_alias TEXT,
ADD COLUMN IF NOT EXISTS city_catalog_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_estado_region
ON rh_candidate_profile (estado_region);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_pais_codigo
ON rh_candidate_profile (pais_codigo);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_city_group
ON rh_candidate_profile (city_group);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_is_foreign_country
ON rh_candidate_profile (is_foreign_country);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_location_requires_ch_validation
ON rh_candidate_profile (location_requires_ch_validation);

COMMIT;
