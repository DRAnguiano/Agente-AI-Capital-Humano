BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS rh_city_catalog (
    id BIGSERIAL PRIMARY KEY,

    alias_text TEXT NOT NULL,
    alias_norm TEXT NOT NULL,

    canonical_city TEXT NOT NULL,
    state_region TEXT,
    country_code TEXT NOT NULL DEFAULT 'MX',
    country_name TEXT NOT NULL DEFAULT 'México',

    city_group TEXT NOT NULL DEFAULT 'Foráneo México',

    is_local_laguna BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_country BOOLEAN NOT NULL DEFAULT FALSE,
    requires_ch_validation BOOLEAN NOT NULL DEFAULT FALSE,
    needs_travel_validation BOOLEAN NOT NULL DEFAULT TRUE,

    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rh_city_catalog_alias_norm_unique UNIQUE (alias_norm)
);

CREATE INDEX IF NOT EXISTS idx_rh_city_catalog_alias_norm
ON rh_city_catalog (alias_norm);

CREATE INDEX IF NOT EXISTS idx_rh_city_catalog_canonical_city
ON rh_city_catalog (canonical_city);

CREATE INDEX IF NOT EXISTS idx_rh_city_catalog_country_code
ON rh_city_catalog (country_code);

CREATE INDEX IF NOT EXISTS idx_rh_city_catalog_city_group
ON rh_city_catalog (city_group);

CREATE INDEX IF NOT EXISTS idx_rh_city_catalog_local_laguna
ON rh_city_catalog (is_local_laguna);

CREATE OR REPLACE FUNCTION rh_norm_text(input_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT lower(trim(unaccent(coalesce(input_text, ''))));
$$;

CREATE OR REPLACE FUNCTION rh_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rh_city_catalog_updated_at ON rh_city_catalog;

CREATE TRIGGER trg_rh_city_catalog_updated_at
BEFORE UPDATE ON rh_city_catalog
FOR EACH ROW
EXECUTE FUNCTION rh_touch_updated_at();

COMMIT;
