declare module "ral-colors" {
  interface ClassicEntry {
    description: string;
    HEX: string;
    rgb: { r: number; g: number; b: number };
    group: string;
  }

  interface EffectGroup {
    id: string;
    rgb: { r: number; g: number; b: number };
  }

  interface EffectEntry {
    description: string;
    groups: EffectGroup[];
  }

  export const RAL: {
    classic: Record<string, ClassicEntry>;
    effect: Record<string, EffectEntry>;
    design_system: Record<string, unknown>;
  };
}
