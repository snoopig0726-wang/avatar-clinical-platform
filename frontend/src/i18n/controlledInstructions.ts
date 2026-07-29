import type { Language } from './LanguageProvider'

type Translator = (source: string) => string

const genericPrefixes = [
  '在非血腥、非伤害且避免极端视觉刺激的边界内，忠实按照患者提出的方向调整：',
  '在非血腥、非伤害且避免极端视觉刺激的边界内，忠实按照患者提出的多个方向调整：',
]

export function localizeControlledInstruction(
  instruction: string,
  t: Translator,
  language: Language,
): string {
  for (const prefix of genericPrefixes) {
    if (instruction.startsWith(prefix)) {
      const originalDirection = instruction.slice(prefix.length).trim()
      return `${t(prefix)} ${originalDirection}`.trim()
    }
  }

  const separator = language === 'en' ? '; ' : '；'
  return instruction
    .split('；')
    .map((item) => t(item.trim()))
    .join(separator)
}
