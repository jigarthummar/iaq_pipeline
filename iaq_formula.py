def iaq_score(temp_c, rh_pct, co2_ppm, tvoc_ppb):
    # ------------ 1. CO₂ & TVOC sub‑index ----------------
    def band(value, limits):                # limits = [upper1, upper2, …]
        for i, lim in enumerate(limits, start=1):
            if value <= lim:
                return i
        return len(limits) + 1              # worst case

    co2_idx  = band(co2_ppm,  [600, 1000, 1500, 2000, 5000])
    tvoc_idx = band(tvoc_ppb, [50, 100, 150, 200, 300])

    # ------------ 2. Temp/Humidity sub‑index --------------
    HUM = [10,20,30,40,50,60,70,80,90]
    TMP = [16,17,18,19,20,21,22,23,24,25,26,27,28]
    GRID = [  # 9 × 13 matrix (rows = HUM, cols = TMP)
        [6,6,6,6,6,6,6,6,6,6,6,6,6],  # 10 %
        [6,5,5,5,5,5,5,5,5,5,5,5,6],  # 20 %
        [6,5,5,4,4,4,4,4,4,4,4,5,6],  # 30 %
        [6,5,5,4,3,3,3,3,2,2,3,5,6],  # 40 %
        [5,5,4,3,2,1,1,1,1,1,1,5,6],  # 50 %
        [5,4,3,2,1,1,1,1,1,2,3,5,6],  # 60 %
        [5,4,3,2,1,1,1,1,2,3,4,5,6],  # 70 %
        [5,4,2,2,2,2,2,3,4,5,5,5,6],  # 80 %
        [6,5,4,3,3,3,3,4,5,5,6,6,6],  # 90 %
    ]

    # locate the surrounding box
    import bisect, numpy as np
    r = min(len(HUM)-2, bisect.bisect_left(HUM, rh_pct)-1)
    c = min(len(TMP)-2, bisect.bisect_left(TMP, temp_c)-1)

    # relative positions 0‑1
    t = (rh_pct - HUM[r]) / (HUM[r+1]-HUM[r])
    u = (temp_c - TMP[c]) / (TMP[c+1]-TMP[c])

    # bilinear interpolation
    th_idx = (
        (1-t)*(1-u)*GRID[r][c]     + (1-t)*u*GRID[r][c+1] +
           t *(1-u)*GRID[r+1][c]   +  t *u*GRID[r+1][c+1]
    )

    # ------------ 3. Sub‑scores & final score ------------
    def to_subscore(idx): return 120 - 20*idx

    sub = {
        'CO2' : to_subscore(co2_idx),
        'TVOC': to_subscore(tvoc_idx),
        'THI' : to_subscore(th_idx)
    }

    iaq = round(0.4*sub['CO2'] + 0.3*sub['TVOC'] + 0.3*sub['THI'])
    iaq = max(0, min(100, iaq))
    return iaq, sub
