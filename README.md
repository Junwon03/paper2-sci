# paper2-sci

SCI (Staking Concentration Index) calculator for IPR Paper 2.

## 📂 파일 구조

```
paper2-sci/
├── sci_calculator_v2.py       # 메인 스크립트
├── requirements.txt            # Python 패키지
├── data/
│   ├── raw/
│   │   └── staking_data.csv   # 입력 데이터
│   └── processed/              # 결과 CSV
├── figures/                    # 결과 그래프
└── docs/                       # 문서
```

## 🚀 빠른 시작

### 1. 설치

```bash
pip install -r requirements.txt
```

### 2. 실행

```bash
python sci_calculator_v2.py
```

기본값:
- Input: `data/raw/staking_data.csv`
- Output: `data/processed/`
- Figures: `figures/`

### 3. 결과 확인

- `figures/figure1_sci_timeseries.png` - Figure 1 (논문용)
- `figures/figure2_staked_by_entity.png` - Figure 2 (논문용)
- `data/processed/table4_sci_summary.csv` - Table 4 (본문용)
- `data/processed/appendix_table_a1_sci_full.csv` - Appendix A1

## 📊 Dune 데이터 사용

### Dune에서 다운로드

1. https://dune.com/hildobby/eth2-staking 접속
2. 쿼리 Fork 후 실행
3. CSV 다운로드

### 데이터 교체

```bash
mv ~/Downloads/query_*.csv data/raw/staking_data.csv
python sci_calculator_v2.py
```

## 🔧 옵션

```bash
# Top N 엔티티 변경
python sci_calculator_v2.py --top-n 15

# 경로 지정
python sci_calculator_v2.py \
  --input my_data.csv \
  --output-dir results \
  --figures-dir images
```

## 📝 데이터 형식

CSV 파일 필수 컬럼:
- `date`: 날짜 (YYYY-MM-DD)
- `entity`: 엔티티 이름
- `staked_eth`: 스테이킹 양

## 📈 출력 메트릭

- **HHI**: Herfindahl-Hirschman Index
- **Nakamoto Coeff.**: 1/3 임계값 기준
- **Norm. Entropy**: 정규화된 Shannon Entropy

## ⚠️ 참고

- Entity-level 데이터 권장 (10+ entities)
- Category-level이면 limitation 추가 필요
- SCI는 서술적 증거, 인과 관계 입증 아님
