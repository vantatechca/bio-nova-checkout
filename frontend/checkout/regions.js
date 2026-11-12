// Country and state/province lists for the shipping address pickers.

const COUNTRY_CODES = (
  'AF AL DZ AD AO AG AR AM AU AT AZ BS BH BD BB BY BE BZ BJ BT BO BA BW BR BN BG BF BI KH CM CA CV CF TD CL CN CO KM CG CD CR CI HR CU CY CZ DK DJ DM DO EC EG SV GQ ER EE SZ ET FJ FI FR GA GM GE DE GH GR GD GT GN GW GY HT HN HK HU IS IN ID IR IQ IE IL IT JM JP JO KZ KE KI KW KG LA LV LB LS LR LY LI LT LU MO MG MW MY MV ML MT MH MR MU MX FM MD MC MN ME MA MZ MM NA NR NP NL NZ NI NE NG KP MK NO OM PK PW PS PA PG PY PE PH PL PT PR QA RO RU RW KN LC VC WS SM ST SA SN RS SC SL SG SK SI SB SO ZA KR SS ES LK SD SR SE CH SY TW TJ TZ TH TL TG TO TT TN TR TM TV UG UA AE GB US UY UZ VU VA VE VN YE ZM ZW'
).split(' ');

/** Country names in English, with Canada and the United States first, then A to Z. */
export function countries() {
  let names;
  try {
    const display = new Intl.DisplayNames(['en'], { type: 'region' });
    names = COUNTRY_CODES.map((code) => display.of(code));
  } catch {
    names = ['Canada', 'United States', 'United Kingdom', 'Australia'];
  }
  const first = ['Canada', 'United States'];
  const rest = names.filter((n) => !first.includes(n)).sort((a, b) => a.localeCompare(b));
  return [...first, ...rest];
}

const US = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'District of Columbia',
  'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
  'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
  'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
  'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia',
  'Washington', 'West Virginia', 'Wisconsin', 'Wyoming', 'American Samoa', 'Guam', 'Northern Mariana Islands',
  'Puerto Rico', 'U.S. Virgin Islands', 'Armed Forces Americas', 'Armed Forces Europe', 'Armed Forces Pacific',
];
const CANADA = [
  'Alberta', 'British Columbia', 'Manitoba', 'New Brunswick', 'Newfoundland and Labrador', 'Northwest Territories',
  'Nova Scotia', 'Nunavut', 'Ontario', 'Prince Edward Island', 'Quebec', 'Saskatchewan', 'Yukon',
];
const AUSTRALIA = [
  'Australian Capital Territory', 'New South Wales', 'Northern Territory', 'Queensland', 'South Australia', 'Tasmania',
  'Victoria', 'Western Australia',
];

const REGIONS = { 'United States': US, Canada: CANADA, Australia: AUSTRALIA };

/** The state/province choices for a country, or null when it has no list (the shopper types it instead). */
export const regionsFor = (country) => REGIONS[country] ?? null;
