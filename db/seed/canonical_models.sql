-- ============================================================
-- Garage Radar — Canonical Models Seed Data
-- Air-cooled Porsche 911: G1–G6 reference table
-- ============================================================

INSERT INTO canonical_models (generation, years_start, years_end, common_name, known_trims, known_engine_variants, comp_weight, notes) VALUES

-- G1: Classic / Long-hood 911 (1965–1973)
('G1', 1965, 1973, 'Classic 911 / Long-hood',
    ARRAY['911', '911T', '911E', '911S', '912', '2.7RS', 'Carrera RS'],
    ARRAY['2.0', '2.2', '2.4', '2.7'],
    1.0,
    'Long-hood era. 912 shares the body but has a 4-cylinder VW engine — comps diverge sharply. 2.7 RS is the blue-chip variant; weight it separately.'
),

-- G2: Impact bumper (1974–1977)
('G2', 1974, 1977, 'Impact bumper Carrera',
    ARRAY['Carrera', '911S', 'Turbo', '930'],
    ARRAY['2.7', '3.0', '3.0T'],
    1.0,
    'US bumper regulations added rubber-tipped bumpers. 930 Turbo introduced 1975. Turbo comps are a separate cluster.'
),

-- G3: SC era (1978–1983)
('G3', 1978, 1983, '911 SC',
    ARRAY['SC', 'SC Targa', 'SC Cabriolet', 'Turbo', '930'],
    ARRAY['3.0', '3.3T'],
    1.0,
    'SC is well-regarded as an entry-level aircooled. Cabriolet introduced 1983 (first cabriolet 911). 930 Turbo separate cluster.'
),

-- G4: Carrera 3.2 (1984–1989)
('G4', 1984, 1989, 'Carrera 3.2',
    ARRAY['Carrera', 'Carrera Targa', 'Carrera Cabriolet', 'Speedster', 'Turbo', '930'],
    ARRAY['3.2', '3.3T'],
    1.0,
    'Carrera 3.2 is the most common G4. Speedster (1989 only) commands significant premium. Turbo production resumed 1988.'
),

-- G5: 964 (1989–1994)
('G5', 1989, 1994, '964',
    ARRAY['Carrera 2', 'Carrera 4', 'Targa', 'Cabriolet', 'Turbo 3.3', 'Turbo 3.6', 'RS America', 'Carrera RS', 'Speedster'],
    ARRAY['3.6', '3.3T', '3.6T'],
    1.0,
    'First major 911 redesign. Carrera 4 = AWD. RS America is lightweight special model unique to US market. C4 comps generally below C2.'
),

-- G6: 993 — Last air-cooled (1994–1998)
('G6', 1994, 1998, '993 — Last air-cooled',
    ARRAY['Carrera', 'Carrera 4', 'Targa', 'Cabriolet', 'Turbo', 'Turbo S', 'Carrera RS', 'Carrera 4S', 'GT2'],
    ARRAY['3.6', '3.6T', '3.8T'],
    1.2,
    'Highest collector demand of all air-cooled generations. Turbo (twin-turbo) is a different comp cluster. GT2 is extremely rare — handle individually. Comp weight 1.2x reflects premium market position.'
);
