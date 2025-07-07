# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Hugo Development Server
```bash
# Start development server (recommended)
mise exec -- hugo server

# Start with drafts and future content
mise exec -- hugo server -D -F

# Build for production
mise exec -- hugo build
```

### Tool Management
This project uses `mise` for tool version management:
- Hugo Extended (latest) - for site generation
- Dart Sass v1.89.1 - for SCSS compilation

## Architecture Overview

### Hugo Site Structure
This is a Hugo static site for Kinderkrippe Olten (German childcare facility) with a sophisticated custom architecture:

**Multi-site Management**: Single Hugo instance managing multiple childcare sites (Sonnhalde, Hagmatt) with color-coded groups and individual identities.

**Block-based Content System**: Content is organized into reusable blocks in `/content/blocks/` rather than traditional Hugo sections:
- Text content blocks (`aufgehoben/`, `aufgeschoben/`)
- Picture circle layouts (`3pics/` with 3-5 circle arrangements)
- Blog reference blocks for different site sections
- Interactive minigame components (3body character builder)

**Doublepage Layout System**: Core layout pattern using `doublepage` shortcode for split-screen designs with configurable:
- Left/right content positioning
- Background colors (beige/yellow)
- Border styles (stripes/yellow/none)

### Key Components

**Templates & Partials**:
- `render-component.html` and `render-block.html` - Dynamic content assembly
- `render-blog-section.html` - Blog slider with horizontal scrolling cards
- `kko-header.html` and `kko-footer.html` - Site-specific headers/footers
- Modal components for images, movies, and downloads

**Styling System**:
- UIKit framework with extensive custom overrides in `/assets/scss/`
- Color-coded theming (`kko-color-*` classes)
- Component-specific SCSS modules (`_kko-*.scss`)
- Responsive design with mobile-first approach

**Interactive Features**:
- Minigames using UIKit sliders (3body character builder)
- Custom animations (brain animation shortcode)
- Modal overlays for media content
- Dynamic SVG loading system

### Data Configuration

**Key Data Files**:
- `data/menu.yaml` - Main navigation and sub-navigation structure
- `data/sites.yaml` - Site definitions with colors and child groups
- `data/footer.yaml` - Footer content configuration

**Blog System**:
- Blog posts in `/content/blog/` with metadata for site/group assignment
- Teaser images and content organization by date
- Horizontal scrolling blog cards with filtering by site

### Asset Management

**Image Processing**:
- Hugo's built-in image processing with WebP conversion
- Resource fingerprinting for cache busting
- SVG icon system with dynamic loading via `get-svg.html`

**SCSS/CSS**:
- Compiled via Hugo's Dart Sass processor
- UIKit integration with custom theme overrides
- Component-specific styling modules

### Content Patterns

**Homepage Structure**: Uses `doublepage` shortcodes to create split-screen layouts with different content blocks.

**Blog Organization**: Posts are organized by site and group with metadata for filtering and display.

**Block Content**: Reusable content blocks that can be rendered in different contexts via the component system.

### Development Notes

- No package.json - pure Hugo setup without Node.js dependencies
- Uses Hugo's built-in asset processing for SCSS compilation
- Extensive use of Hugo's data files for configuration
- Custom shortcode system for complex layouts
- Multi-language support configured for German (de-ch)

When making changes, be aware of the interconnected nature of the block system, data files, and custom shortcodes. The site relies heavily on the relationship between content blocks, site definitions, and the rendering system.