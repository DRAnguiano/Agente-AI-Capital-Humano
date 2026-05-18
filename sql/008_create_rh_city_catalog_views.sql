BEGIN;
CREATE OR REPLACE VIEW v_rh_city_catalog AS  SELECT id,
    alias_text,
    alias_norm,
    canonical_city,
    state_region,
    country_code,
    country_name,
    city_group,
    is_local_laguna,
    is_foreign_country,
    requires_ch_validation,
    needs_travel_validation,
    notes,
    created_at,
    updated_at
   FROM rh_city_catalog;;
COMMIT;
