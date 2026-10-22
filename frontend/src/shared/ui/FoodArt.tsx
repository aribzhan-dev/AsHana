// Illustrations stand in for product photos: uploads are not implemented yet.
type Art = { tint: string; body: React.ReactNode };

const plate = (
  <>
    <ellipse cx="60" cy="66" rx="40" ry="14" fill="#ffffff" opacity="0.9" />
    <ellipse cx="60" cy="62" rx="32" ry="10" fill="#f1e6d2" />
  </>
);
const arts: Record<string, Art> = {
  bowl: {
    tint: "#2f4a35",
    body: (
      <>
        <path d="M22 54h76a38 22 0 0 1-76 0Z" fill="#f7f2e8" />
        <ellipse cx="60" cy="54" rx="38" ry="9" fill="#c98a3c" />
        <circle cx="48" cy="50" r="7" fill="#e3a35a" />
        <circle cx="62" cy="47" r="6" fill="#d98f41" />
        <circle cx="74" cy="51" r="5" fill="#7fae5a" />
        <circle cx="54" cy="55" r="4" fill="#f0b04a" />
        <circle cx="70" cy="56" r="3.5" fill="#5e8f43" />
      </>
    ),
  },
  soup: {
    tint: "#5a3b22",
    body: (
      <>
        <path
          d="M46 26c-4 5 4 7 0 12M60 22c-4 5 4 7 0 12M74 26c-4 5 4 7 0 12"
          stroke="#ffffff"
          strokeOpacity="0.6"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
        />
        <path d="M24 50h72a36 24 0 0 1-72 0Z" fill="#f7f2e8" />
        <ellipse cx="60" cy="50" rx="36" ry="8" fill="#e6a640" />
        <circle cx="50" cy="49" r="3" fill="#f6d27a" />
        <circle cx="66" cy="51" r="3" fill="#e57f3d" />
      </>
    ),
  },
  salad: {
    tint: "#2e5a3a",
    body: (
      <>
        <path d="M24 54h72a36 20 0 0 1-72 0Z" fill="#f7f2e8" />
        <ellipse cx="44" cy="50" rx="12" ry="8" fill="#7cc061" />
        <ellipse cx="62" cy="47" rx="12" ry="8" fill="#5fa84a" />
        <circle cx="76" cy="52" r="6" fill="#e2493b" />
        <circle cx="54" cy="54" r="5" fill="#ef6a4d" />
        <ellipse cx="68" cy="56" rx="6" ry="3" fill="#cfe7a4" />
      </>
    ),
  },
  pastry: {
    tint: "#6b4520",
    body: (
      <>
        {plate}
        <path
          d="M30 60c6-18 54-18 60 0-8 6-52 6-60 0Z"
          fill="#e7a24d"
          stroke="#c47c2c"
          strokeWidth="2"
        />
        <path
          d="M44 50l4 12M60 46v15M76 50l-4 12"
          stroke="#c47c2c"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </>
    ),
  },
  drink: {
    tint: "#1f4e66",
    body: (
      <>
        <path d="M44 30h32l-4 46H48Z" fill="#ffffff" opacity="0.9" />
        <path d="M46 46h28l-2.6 30H48.6Z" fill="#f2b33d" />
        <path d="M66 20l-4 16" stroke="#ffffff" strokeWidth="3" />
      </>
    ),
  },
  dessert: {
    tint: "#6a3550",
    body: (
      <>
        <path d="M40 42h40l-6 34H46Z" fill="#ffffff" />
        <ellipse cx="60" cy="42" rx="20" ry="6" fill="#f7e9f0" />
        <circle cx="54" cy="38" r="5" fill="#e0527a" />
        <circle cx="66" cy="39" r="4" fill="#7b3fa0" />
      </>
    ),
  },
  side: {
    tint: "#4b4a2c",
    body: (
      <>
        {plate}
        <ellipse cx="56" cy="56" rx="20" ry="9" fill="#f6e3a8" />
        <ellipse cx="74" cy="58" rx="8" ry="4" fill="#7fae5a" />
      </>
    ),
  },
};

function pick(category: string, name: string): Art {
  const text = `${category} ${name}`.toLowerCase();
  if (/суп|борщ|бульон/.test(text)) return arts.soup!;
  if (/салат/.test(text)) return arts.salad!;
  if (/выпеч|самса|круассан|хлеб|пирож|булоч/.test(text)) return arts.pastry!;
  if (/напит|сок|вода|чай|кофе|компот/.test(text)) return arts.drink!;
  if (/десерт|йогурт|торт/.test(text)) return arts.dessert!;
  if (/гарнир|пюре/.test(text)) return arts.side!;
  return arts.bowl!;
}

export function FoodArt({
  category,
  name,
  className = "",
}: {
  category: string;
  name: string;
  className?: string;
}) {
  const art = pick(category, name);
  return (
    <svg
      className={`food-art ${className}`}
      viewBox="0 0 120 90"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="120" height="90" fill={art.tint} />
      <circle cx="100" cy="14" r="28" fill="#ffffff" opacity="0.06" />
      {art.body}
    </svg>
  );
}
