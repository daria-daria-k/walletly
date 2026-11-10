import { CategoryIcon } from '../components/CategoryIcon';

const GROUPS = [
  {
    number: '01',
    title: 'Базовые расходы',
    subtitle: 'Регулярные и обязательные платежи',
    categories: ['Продукты', 'Жильё и аренда', 'Коммунальные услуги', 'Транспорт', 'Связь и интернет', 'Здоровье и лекарства', 'Страхование', 'Образование', 'Дети', 'Кредиты и рассрочки', 'Налоги', 'Домашние животные'],
  },
  {
    number: '02',
    title: 'Текущие расходы',
    subtitle: 'Повседневные и необязательные траты',
    categories: ['Кафе и рестораны', 'Доставка еды', 'Одежда и обувь', 'Красота и уход', 'Развлечения', 'Подписки и сервисы', 'Такси', 'Спорт и фитнес', 'Хобби', 'Подарки', 'Путешествия', 'Маркетплейсы', 'Товары для дома', 'Благотворительность', 'Прочее'],
  },
  {
    number: '03',
    title: 'Крупные расходы и цели',
    subtitle: 'Планируемые покупки и накопления',
    categories: ['Отпуск', 'Ремонт', 'Автомобиль', 'Недвижимость', 'Бытовая техника', 'Электроника', 'Мебель', 'Образование', 'Свадьба', 'Переезд', 'Медицинские расходы', 'Финансовая подушка', 'Досрочное погашение кредита', 'Инвестиции', 'Собственный проект'],
  },
];

export function CategoryIconsPage() {
  return (
    <main className="icon-gallery" data-theme="violet">
      <header className="icon-gallery-hero">
        <div className="icon-gallery-brand"><img src="/brand/walletly-mark.svg" alt="" /><span>Walletly</span></div>
        <p className="eyebrow">Система категорий</p>
        <h1>Иконки расходов</h1>
        <p>Цвет помогает быстрее находить категорию, а символ — узнавать её без чтения подписи.</p>
      </header>

      <div className="icon-gallery-groups">
        {GROUPS.map((group) => (
          <section className="icon-gallery-group" key={group.number}>
            <div className="icon-gallery-heading">
              <span>{group.number}</span>
              <div><h2>{group.title}</h2><p>{group.subtitle}</p></div>
            </div>
            <div className="icon-gallery-grid">
              {group.categories.map((category) => (
                <article className="icon-gallery-card" key={`${group.number}-${category}`}>
                  <CategoryIcon name={category} />
                  <div><h3>{category}</h3><p>{group.title}</p></div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
