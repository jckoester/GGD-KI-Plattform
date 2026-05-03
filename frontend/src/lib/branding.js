export const branding = {
  name: import.meta.env.PUBLIC_SCHOOL_NAME || 'ki@schule',
  logo_url_light: import.meta.env.PUBLIC_SCHOOL_LOGO_URL_LIGHT
                  || import.meta.env.PUBLIC_SCHOOL_LOGO_URL
                  || null,
  logo_url_dark:  import.meta.env.PUBLIC_SCHOOL_LOGO_URL_DARK
                  || import.meta.env.PUBLIC_SCHOOL_LOGO_URL
                  || null,
};
