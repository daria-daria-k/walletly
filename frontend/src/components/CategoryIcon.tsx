import {
  Armchair, Baby, BadgeDollarSign, Banknote, BriefcaseBusiness, Building2,
  Bus, CalendarSync, CarFront, CarTaxiFront, ChartNoAxesCombined, CircleEllipsis, Clapperboard, Dumbbell,
  Gamepad2, Gem, Gift, GraduationCap, HandCoins, HandPlatter, HeartHandshake, HeartPulse,
  House, HousePlug, Landmark, Laptop, Package, PaintRoller, Palmtree, PawPrint,
  PiggyBank, Plane, ReceiptText, Repeat2, Rocket, Scissors, Shirt,
  ShoppingCart, Smartphone, Sofa, Sparkles, Stethoscope, Truck, UtensilsCrossed,
  Umbrella, WashingMachine,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { CSSProperties } from 'react';

type IconSpec = { icon: LucideIcon; color: string; accent: string };

// Цвет — часть идентичности категории: он стабилен на всех экранах и не зависит от порядка.
const ICONS: Record<string, IconSpec> = {
  'продукты': { icon: ShoppingCart, color: '#55B89A', accent: '#F2C75C' },
  'жильё и аренда': { icon: House, color: '#7E73D8', accent: '#F0A765' },
  'коммунальные услуги': { icon: HousePlug, color: '#E2A23A', accent: '#55A9C5' },
  'транспорт': { icon: Bus, color: '#4F91D8', accent: '#F4B45E' },
  'связь и интернет': { icon: Smartphone, color: '#6577D8', accent: '#65C8B0' },
  'здоровье и лекарства': { icon: HeartPulse, color: '#E06F7D', accent: '#78C6A3' },
  'страхование': { icon: Umbrella, color: '#5289C7', accent: '#F0B65C' },
  'образование': { icon: GraduationCap, color: '#6E78D5', accent: '#F0C35B' },
  'дети': { icon: Baby, color: '#E78EAD', accent: '#71B9D4' },
  'кредиты и рассрочки': { icon: HandCoins, color: '#D58A59', accent: '#E7C654' },
  'налоги': { icon: Landmark, color: '#74859C', accent: '#D8A25B' },
  'домашние животные': { icon: PawPrint, color: '#B07A62', accent: '#72BFA5' },

  'кафе и рестораны': { icon: UtensilsCrossed, color: '#55B89A', accent: '#F2C75C' },
  'доставка еды': { icon: HandPlatter, color: '#E78A55', accent: '#62B8B0' },
  'одежда и обувь': { icon: Shirt, color: '#8B72D0', accent: '#EBA0B5' },
  'красота и уход': { icon: Scissors, color: '#DB77A8', accent: '#F1C45D' },
  'развлечения': { icon: Clapperboard, color: '#7766C8', accent: '#EE8D75' },
  'подписки и сервисы': { icon: CalendarSync, color: '#6D70CF', accent: '#61BEA5' },
  'такси': { icon: CarTaxiFront, color: '#E2AA3C', accent: '#5B6475' },
  'спорт и фитнес': { icon: Dumbbell, color: '#E06B65', accent: '#60B9A8' },
  'хобби': { icon: Gamepad2, color: '#9A70CF', accent: '#EFAF59' },
  'подарки': { icon: Gift, color: '#E06E8B', accent: '#6EC1A6' },
  'путешествия': { icon: Plane, color: '#4F9AC8', accent: '#F0B55F' },
  'маркетплейсы': { icon: Package, color: '#736BD0', accent: '#E68C74' },
  'товары для дома': { icon: Sofa, color: '#B17C5F', accent: '#74BFA1' },
  'благотворительность': { icon: HeartHandshake, color: '#DA7182', accent: '#E9B858' },
  'прочее': { icon: CircleEllipsis, color: '#8792A3', accent: '#68BDA5' },

  'отпуск': { icon: Palmtree, color: '#42A9AA', accent: '#F2BE55' },
  'ремонт': { icon: PaintRoller, color: '#D17D56', accent: '#738CD2' },
  'автомобиль': { icon: CarFront, color: '#517FC1', accent: '#E8B553' },
  'недвижимость': { icon: Building2, color: '#687B96', accent: '#69BE9F' },
  'бытовая техника': { icon: WashingMachine, color: '#55A1BD', accent: '#E7B75D' },
  'электроника': { icon: Laptop, color: '#6673C6', accent: '#62C0AB' },
  'мебель': { icon: Armchair, color: '#A7775D', accent: '#78BDA0' },
  'свадьба': { icon: Gem, color: '#C978A9', accent: '#F0C45E' },
  'переезд': { icon: Truck, color: '#D17D55', accent: '#5DB2BB' },
  'медицинские расходы': { icon: Stethoscope, color: '#D96876', accent: '#65BDA0' },
  'финансовая подушка': { icon: PiggyBank, color: '#55AB8D', accent: '#F0BD59' },
  'досрочное погашение кредита': { icon: BadgeDollarSign, color: '#4FAF8F', accent: '#7583D1' },
  'инвестиции': { icon: ChartNoAxesCombined, color: '#4D9C85', accent: '#E7B64E' },
  'собственный проект': { icon: Rocket, color: '#7068CE', accent: '#EC8B6E' },

  // Совместимость с текущим шаблоном и доходными категориями.
  'жильё и жкх': { icon: House, color: '#7E73D8', accent: '#F0A765' },
  'здоровье': { icon: HeartPulse, color: '#E06F7D', accent: '#78C6A3' },
  'красота': { icon: Sparkles, color: '#DB77A8', accent: '#F1C45D' },
  'подписки': { icon: Repeat2, color: '#527CC8', accent: '#69C2A4' },
  'техника': { icon: Laptop, color: '#6673C6', accent: '#62C0AB' },
  'ремонт и мебель': { icon: PaintRoller, color: '#D17D56', accent: '#738CD2' },
  'обучение': { icon: GraduationCap, color: '#6E78D5', accent: '#F0C35B' },
  'зарплата': { icon: BriefcaseBusiness, color: '#48A881', accent: '#E8B852' },
  'подработка': { icon: HandCoins, color: '#6295C5', accent: '#EDB65B' },
  'кешбэк и проценты': { icon: Banknote, color: '#55A77E', accent: '#F0C05A' },
  'прочие доходы': { icon: Banknote, color: '#5AA486', accent: '#7F7AD1' },
};

export const CATEGORY_ICON_OPTIONS = [
  'Продукты', 'Жильё и аренда', 'Коммунальные услуги', 'Транспорт', 'Связь и интернет',
  'Здоровье и лекарства', 'Страхование', 'Образование', 'Дети', 'Кредиты и рассрочки',
  'Налоги', 'Домашние животные', 'Кафе и рестораны', 'Доставка еды', 'Одежда и обувь',
  'Красота и уход', 'Развлечения', 'Подписки и сервисы', 'Такси', 'Спорт и фитнес',
  'Хобби', 'Подарки', 'Путешествия', 'Маркетплейсы', 'Товары для дома',
  'Благотворительность', 'Прочее', 'Отпуск', 'Ремонт', 'Автомобиль', 'Недвижимость',
  'Бытовая техника', 'Электроника', 'Мебель', 'Свадьба', 'Переезд',
  'Медицинские расходы', 'Финансовая подушка', 'Досрочное погашение кредита',
  'Инвестиции', 'Собственный проект',
] as const;

function normalize(name?: string) {
  return (name ?? '').trim().toLocaleLowerCase('ru-RU');
}

function categorySpec(name?: string, iconKey?: string | null, type: 'income' | 'expense' | 'transfer' = 'expense') {
  return type === 'transfer'
    ? { icon: Repeat2, color: '#6577D8', accent: '#65C8B0' }
    : ICONS[normalize(iconKey || name)] ?? (type === 'income'
      ? { icon: Banknote, color: '#4FAE91', accent: '#F0C35B' }
      : { icon: ReceiptText, color: '#8792A3', accent: '#68BDA5' });
}

export function CategoryIcon({ name, iconKey, type = 'expense', size = 'regular' }: { name?: string; iconKey?: string | null; type?: 'income' | 'expense' | 'transfer'; size?: 'small' | 'regular' }) {
  const spec = categorySpec(name, iconKey, type);
  const Icon = spec.icon;
  const style = { '--category-color': spec.color, '--category-accent': spec.accent } as CSSProperties;

  return (
    <span className={`category-icon category-icon-${size}`} style={style} aria-hidden="true">
      <span className="category-icon-core"><Icon /></span>
      <span className="category-icon-accent" />
    </span>
  );
}

export function CategoryTag({ name, iconKey, type = 'expense' }: { name?: string; iconKey?: string | null; type?: 'income' | 'expense' | 'transfer' }) {
  const spec = categorySpec(name, iconKey, type);
  const style = { '--category-color': spec.color } as CSSProperties;
  return <span className="category-tag" style={style}>{type === 'transfer' ? 'Перевод' : name}</span>;
}
