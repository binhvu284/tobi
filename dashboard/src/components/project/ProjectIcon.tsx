import {
  Rocket, Lightbulb, Folder, Target, BarChart3, Wrench, Sprout, FlaskConical,
  Smartphone, Briefcase, Palette, Building2, Zap, Lock, Globe2, TestTube2,
  FileText, Bot, Gamepad2, GraduationCap, HeartPulse, Home, Landmark, Megaphone,
  Music, Newspaper, Package, PenTool, Plane, ShoppingCart, Star, Store, Truck,
  Tv, Wallet, Camera, Code2, Coffee, Database, Dumbbell, type LucideIcon,
} from 'lucide-react'
import type { PMProject } from '../../api.pm'
import { pmIconUrl } from '../../api'

/** Curated vector pack for project icons (#12 D53) — key ↔ lucide component. */
export const ICON_PACK: Record<string, LucideIcon> = {
  rocket: Rocket, lightbulb: Lightbulb, folder: Folder, target: Target,
  chart: BarChart3, wrench: Wrench, sprout: Sprout, flask: FlaskConical,
  phone: Smartphone, briefcase: Briefcase, palette: Palette, building: Building2,
  zap: Zap, lock: Lock, globe: Globe2, test: TestTube2, file: FileText, bot: Bot,
  game: Gamepad2, learn: GraduationCap, health: HeartPulse, home: Home,
  bank: Landmark, megaphone: Megaphone, music: Music, news: Newspaper,
  package: Package, pen: PenTool, plane: Plane, cart: ShoppingCart, star: Star,
  store: Store, truck: Truck, tv: Tv, wallet: Wallet, camera: Camera,
  code: Code2, coffee: Coffee, database: Database, gym: Dumbbell,
}

/** Renders a project's icon whatever its type: emoji (default), icon-pack key, or
 * custom uploaded image (served from the DB via /api/pm/icons/{id}). */
export default function ProjectIcon({ project, size = 24, className = '' }: {
  project: { emoji_icon?: string; icon_type?: 'emoji' | 'icon' | 'custom'; icon_value?: string | null; accent_color?: string | null }
  size?: number
  className?: string
}) {
  const type = project.icon_type || 'emoji'
  if (type === 'custom' && project.icon_value) {
    return (
      <img src={pmIconUrl(project.icon_value)} alt="" width={size} height={size}
        className={`shrink-0 rounded-md object-cover ${className}`} style={{ width: size, height: size }} />
    )
  }
  if (type === 'icon' && project.icon_value && ICON_PACK[project.icon_value]) {
    const Icon = ICON_PACK[project.icon_value]
    return (
      <span className={`flex shrink-0 items-center justify-center ${className}`}
        style={{ width: size, height: size, color: project.accent_color || 'rgb(var(--accent))' }}>
        <Icon size={Math.round(size * 0.86)} />
      </span>
    )
  }
  return (
    <span className={`shrink-0 leading-none ${className}`} style={{ fontSize: size * 0.92 }}>
      {(type === 'emoji' && project.icon_value) || project.emoji_icon || '📁'}
    </span>
  )
}
