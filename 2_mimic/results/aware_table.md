# MIMIC-IV 초기 경험적 요법의 WHO AWaRe 분포 (WHO AWaRe 2025 분류, 4_guideline/pdf/W02.pdf)

## 집단별
| 집단 | 환자 n | 요법 있음 | 성분 건수 | Access % | Watch % | Reserve % | 환자: Access만 % | 환자: Watch 포함 % | 환자: Reserve 포함 % | Watch 상위 3 | Reserve 상위 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pneumonia | 4,875 | 4,875 | 12,508 | 14.1 | 84.9 | 1.0 | 5.4 | 94.4 | 2.4 | vancomycin 63.0%, cefepime 36.1%, azithromycin 32.4% | aztreonam 1.2%, linezolid 0.8%, daptomycin 0.4% |
| uti | 4,523 | 4,523 | 8,557 | 20.2 | 78.3 | 1.5 | 10.9 | 88.7 | 2.6 | vancomycin 40.2%, ceftriaxone 36.7%, ciprofloxacin 19.2% | linezolid 1.1%, aztreonam 0.8%, daptomycin 0.6% |

(성분 건수 = 환자별 초기 요법의 성분 수 합. 환자 기준 % 의 분모 = 요법 있는 환자. 분류 = WHO AWaRe 2025, fosfomycin · minocycline 은 경구/정맥으로 구분)

## 집단 × sepsis3
| 집단 | sepsis3 | 환자 n | 요법 있음 | 성분 건수 | Access % | Watch % | Reserve % | 환자: Access만 % | 환자: Watch 포함 % | 환자: Reserve 포함 % | Watch 상위 3 | Reserve 상위 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pneumonia | 0 | 1,209 | 1,209 | 2,864 | 13.7 | 85.4 | 0.8 | 5.0 | 94.8 | 1.8 | vancomycin 50.4%, azithromycin 37.6%, ceftriaxone 37.1% | aztreonam 1.0%, linezolid 0.6%, daptomycin 0.3% |
| pneumonia | 1 | 3,666 | 3,666 | 9,644 | 14.3 | 84.7 | 1.0 | 5.5 | 94.3 | 2.5 | vancomycin 67.2%, cefepime 38.6%, azithromycin 30.7% | aztreonam 1.3%, linezolid 0.8%, daptomycin 0.5% |
| uti | 0 | 1,343 | 1,343 | 2,091 | 25.1 | 73.5 | 1.4 | 16.8 | 82.9 | 2.1 | ceftriaxone 38.6%, ciprofloxacin 24.0%, vancomycin 23.9% | linezolid 0.9%, daptomycin 0.5%, aztreonam 0.5% |
| uti | 1 | 3,180 | 3,180 | 6,466 | 18.7 | 79.8 | 1.5 | 8.4 | 91.1 | 2.8 | vancomycin 47.1%, ceftriaxone 35.8%, cefepime 21.7% | linezolid 1.2%, aztreonam 0.9%, daptomycin 0.7% |

(성분 건수 = 환자별 초기 요법의 성분 수 합. 환자 기준 % 의 분모 = 요법 있는 환자. 분류 = WHO AWaRe 2025, fosfomycin · minocycline 은 경구/정맥으로 구분)

## 집단 × 입원 시기
| 집단 | admission_era | 환자 n | 요법 있음 | 성분 건수 | Access % | Watch % | Reserve % | 환자: Access만 % | 환자: Watch 포함 % | 환자: Reserve 포함 % | Watch 상위 3 | Reserve 상위 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pneumonia | 2008 - 2010 | 1,519 | 1,519 | 3,862 | 13.3 | 85.7 | 1.1 | 4.0 | 95.7 | 2.6 | vancomycin 61.4%, levofloxacin 33.6%, ceftriaxone 30.0% | aztreonam 1.7%, linezolid 0.7%, daptomycin 0.3% |
| pneumonia | 2011 - 2013 | 1,005 | 1,005 | 2,621 | 13.1 | 85.6 | 1.3 | 5.6 | 94.2 | 3.2 | vancomycin 66.3%, cefepime 39.0%, azithromycin 29.4% | aztreonam 1.3%, linezolid 1.2%, daptomycin 0.6% |
| pneumonia | 2014 - 2016 | 966 | 966 | 2,500 | 13.7 | 85.4 | 0.9 | 5.2 | 94.6 | 2.1 | vancomycin 65.7%, cefepime 43.4%, azithromycin 31.5% | aztreonam 1.2%, linezolid 0.4%, daptomycin 0.3% |
| pneumonia | 2017 - 2019 | 821 | 821 | 2,145 | 14.9 | 84.2 | 0.9 | 7.2 | 92.7 | 2.1 | vancomycin 63.6%, azithromycin 41.5%, cefepime 35.6% | linezolid 0.9%, daptomycin 0.6%, aztreonam 0.6% |
| pneumonia | 2020 - 2022 | 564 | 564 | 1,380 | 18.3 | 81.1 | 0.6 | 6.2 | 93.6 | 1.1 | vancomycin 55.9%, ceftriaxone 42.9%, cefepime 38.5% | daptomycin 0.5%, linezolid 0.5%, aztreonam 0.4% |
| uti | 2008 - 2010 | 1,510 | 1,510 | 2,932 | 19.6 | 78.7 | 1.6 | 10.1 | 89.5 | 3.0 | vancomycin 42.1%, ciprofloxacin 30.3%, ceftriaxone 26.4% | aztreonam 1.2%, linezolid 1.1%, daptomycin 0.7% |
| uti | 2011 - 2013 | 961 | 961 | 1,815 | 20.1 | 78.2 | 1.7 | 11.9 | 87.4 | 3.2 | vancomycin 38.5%, ceftriaxone 35.6%, ciprofloxacin 22.5% | aztreonam 1.1%, linezolid 1.0%, daptomycin 0.7% |
| uti | 2014 - 2016 | 883 | 883 | 1,659 | 20.7 | 77.8 | 1.4 | 12.3 | 87.5 | 2.3 | vancomycin 41.3%, ceftriaxone 40.2%, cefepime 19.5% | linezolid 1.1%, daptomycin 0.7%, aztreonam 0.7% |
| uti | 2017 - 2019 | 747 | 747 | 1,389 | 20.2 | 78.8 | 1.1 | 9.8 | 90.0 | 1.7 | ceftriaxone 47.1%, vancomycin 39.2%, cefepime 19.0% | linezolid 1.2%, daptomycin 0.5%, ceftazidime/avibactam 0.1% |
| uti | 2020 - 2022 | 422 | 422 | 762 | 21.9 | 77.0 | 1.0 | 10.2 | 89.1 | 1.9 | ceftriaxone 50.2%, vancomycin 36.5%, cefepime 23.5% | linezolid 1.2%, daptomycin 0.5%, aztreonam 0.2% |

(성분 건수 = 환자별 초기 요법의 성분 수 합. 환자 기준 % 의 분모 = 요법 있는 환자. 분류 = WHO AWaRe 2025, fosfomycin · minocycline 은 경구/정맥으로 구분)
