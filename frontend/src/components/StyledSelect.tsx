import { Select } from '@base-ui/react/select';
import { Check, ChevronDown } from 'lucide-react';

export interface Option {
  value: string;
  label: string;
}

export interface OptionGroup {
  label: string;
  options: Option[];
}

// Пустая строка в Select означала бы «ничего не выбрано», а у нас это обычный пункт «Все счета»
const EMPTY = '__empty__';
const encode = (value: string) => value || EMPTY;

interface Props {
  value: string;
  onChange: (value: string) => void;
  options?: Option[];
  groups?: OptionGroup[];
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
}

function Item({ option }: { option: Option }) {
  return (
    <Select.Item className="walletly-select-item" value={encode(option.value)}>
      <Select.ItemText>{option.label}</Select.ItemText>
      <Select.ItemIndicator className="walletly-select-indicator"><Check size={15} /></Select.ItemIndicator>
    </Select.Item>
  );
}

export function StyledSelect({ value, onChange, options = [], groups = [], ariaLabel, placeholder = 'Выберите', disabled }: Props) {
  const selected = [...options, ...groups.flatMap((group) => group.options)].find((option) => option.value === value);

  return (
    <Select.Root value={selected ? encode(value) : null} onValueChange={(next) => onChange(next === EMPTY ? '' : String(next))} disabled={disabled}>
      <Select.Trigger className="walletly-select-trigger" aria-label={ariaLabel}>
        {/* Подпись считаем сами: Select знает значения пунктов только после открытия списка */}
        <span className={selected ? '' : 'walletly-select-placeholder'}>{selected?.label ?? placeholder}</span>
        <Select.Icon><ChevronDown size={16} /></Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner className="walletly-select-positioner" alignItemWithTrigger={false} align="start" sideOffset={6}>
          <Select.Popup className="walletly-select-content">
            <Select.List>
              {options.map((option) => <Item key={option.value} option={option} />)}
              {groups.map((group) => (
                <Select.Group key={group.label}>
                  <Select.GroupLabel className="walletly-select-group-label">{group.label}</Select.GroupLabel>
                  {group.options.map((option) => <Item key={option.value} option={option} />)}
                </Select.Group>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
