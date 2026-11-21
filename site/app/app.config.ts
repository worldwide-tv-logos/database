export default defineAppConfig({
  ui: {
    colors: {
      primary: 'blue',
      secondary: 'violet',
      neutral: 'zinc'
    },
    footer: {
      slots: {
        root: 'border-t border-default',
        left: 'text-sm text-muted'
      }
    }
  },
  seo: {
    siteName: 'Worldwide TV Logos'
  },
  repo: 'https://github.com/worldwide-tv-logos/database',
  toc: {
    title: 'On this page',
    bottom: {
      title: 'Project',
      edit: 'https://github.com/worldwide-tv-logos/database/edit/main/site/content',
      links: [{
        icon: 'i-lucide-message-square-plus',
        label: 'Request a logo',
        to: 'https://github.com/worldwide-tv-logos/database/issues/new?template=04_logos_request.yml',
        target: '_blank'
      }, {
        icon: 'i-simple-icons-github',
        label: 'Repository',
        to: 'https://github.com/worldwide-tv-logos/database',
        target: '_blank'
      }]
    }
  }
})
