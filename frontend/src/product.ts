export type ProductProfile = {
  id: string;
  displayName: string;
  frameworkName: string;
  tagline: string;
  heroImage: string;
};

const env = import.meta.env;

/**
 * User-facing product shell configuration.
 *
 * Framework components consume this profile instead of hard-coding one product
 * name. A separate deployment can replace the shell through Vite environment
 * variables while continuing to use the same AgentForge frontend framework.
 */
export const PRODUCT: ProductProfile = Object.freeze({
  id: env.VITE_PRODUCT_ID?.trim() || "sodateru_app",
  displayName: env.VITE_PRODUCT_NAME?.trim() || "育てるアプリ",
  frameworkName: env.VITE_FRAMEWORK_NAME?.trim() || "AgentForge",
  tagline: env.VITE_PRODUCT_TAGLINE?.trim() || "会話で作って、使いながら育てる",
  heroImage: env.VITE_PRODUCT_HERO_IMAGE?.trim() || "/sodateru-app-title-880x495.png",
});

export const poweredByLabel = `powered by ${PRODUCT.frameworkName}`;
export const productTitleVisualAlt = `${PRODUCT.displayName}のタイトルビジュアル`;
export const productAdminTitle = `${PRODUCT.displayName} 管理`;
