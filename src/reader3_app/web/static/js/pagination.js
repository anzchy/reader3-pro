/**
 * Pagination Module for Full-Screen Paginated Reader
 *
 * Implements horizontal pagination using CSS Multi-column Layout with:
 * - Keyboard navigation (←/→ arrow keys)
 * - Click zone navigation (left/right edges)
 * - Reading progress indicator
 * - Resize position preservation
 * - Mobile fallback detection
 */

(function() {
    'use strict';

    // Configuration from CSS variables
    const MIN_PAGINATION_WIDTH = 600;

    // DOM Elements
    let container = null;
    let content = null;
    let progressIndicator = null;
    let navZoneLeft = null;
    let navZoneRight = null;
    let prevChapterLink = null;
    let nextChapterLink = null;

    // State
    let currentPage = 0;
    let totalPages = 1;
    let pageWidth = 0;
    let isInitialized = false;
    let resizeTimer = null;
    let scrollPercentage = 0;

    // Layout constants (match CSS variables)
    const READER_MARGIN_X = 80;

    /**
     * Check if pagination should be enabled based on viewport width
     */
    function isPaginationEnabled() {
        return window.innerWidth >= MIN_PAGINATION_WIDTH;
    }

    /**
     * Check if there's an active text selection
     */
    function hasActiveSelection() {
        const selection = window.getSelection();
        return selection && selection.toString().trim().length > 0;
    }

    /**
     * Update column width dynamically to ensure exactly one column per page
     * This fixes the issue where CSS calc with 100vw can cause multiple columns
     */
    function updateColumnWidth() {
        if (!container || !content) return;

        // Get actual container width
        const containerWidth = container.clientWidth;

        // Calculate the column width (container width minus left+right margins)
        const columnWidth = containerWidth - (READER_MARGIN_X * 2);

        // Set column-width explicitly to ensure exactly one column per viewport
        content.style.columnWidth = `${columnWidth}px`;

        // Column gap should be double the margin so pages align correctly
        content.style.columnGap = `${READER_MARGIN_X * 2}px`;

        console.log(`Pagination: Column width set to ${columnWidth}px (container: ${containerWidth}px)`);
    }

    /**
     * Calculate total number of pages based on scroll width
     */
    function calculatePages() {
        if (!container || !content) return;

        pageWidth = container.clientWidth;
        const scrollWidth = content.scrollWidth;
        totalPages = Math.max(1, Math.ceil(scrollWidth / pageWidth));

        // Update current page based on scroll position
        currentPage = Math.round(container.scrollLeft / pageWidth);
        currentPage = Math.max(0, Math.min(currentPage, totalPages - 1));
    }

    /**
     * Navigate to a specific page number
     */
    function navigateToPage(pageNum) {
        if (!container || !isPaginationEnabled()) return;

        // Clamp page number
        pageNum = Math.max(0, Math.min(pageNum, totalPages - 1));

        // Calculate scroll position
        const scrollLeft = pageNum * pageWidth;

        // Smooth scroll to page
        container.scrollTo({
            left: scrollLeft,
            behavior: 'smooth'
        });

        currentPage = pageNum;
        updateProgress();
    }

    /**
     * Navigate to next page
     */
    function nextPage() {
        if (currentPage >= totalPages - 1) {
            // At last page, navigate to next chapter if available
            if (nextChapterLink) {
                nextChapterLink.click();
            }
            return;
        }
        navigateToPage(currentPage + 1);
    }

    /**
     * Navigate to previous page
     */
    function prevPage() {
        if (currentPage <= 0) {
            // At first page, navigate to previous chapter if available
            if (prevChapterLink) {
                prevChapterLink.click();
            }
            return;
        }
        navigateToPage(currentPage - 1);
    }

    /**
     * Update the reading progress indicator
     */
    function updateProgress() {
        if (!progressIndicator) return;

        // Calculate percentage
        let percentage;
        if (totalPages <= 1) {
            percentage = 100;
        } else {
            percentage = Math.round(((currentPage + 1) / totalPages) * 100);
        }

        progressIndicator.textContent = `当前阅读至 ${percentage}%`;
    }

    /**
     * Handle keyboard navigation
     */
    function handleKeydown(e) {
        if (!isPaginationEnabled()) return;

        // Don't handle if user is typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        switch (e.key) {
            case 'ArrowRight':
            case 'PageDown':
                e.preventDefault();
                nextPage();
                break;
            case 'ArrowLeft':
            case 'PageUp':
                e.preventDefault();
                prevPage();
                break;
            case 'Home':
                e.preventDefault();
                navigateToPage(0);
                break;
            case 'End':
                e.preventDefault();
                navigateToPage(totalPages - 1);
                break;
        }
    }

    /**
     * Handle scroll events to update current page and progress
     */
    function handleScroll() {
        if (!container || !isPaginationEnabled()) return;

        // Calculate current page from scroll position
        const newPage = Math.round(container.scrollLeft / pageWidth);
        if (newPage !== currentPage) {
            currentPage = Math.max(0, Math.min(newPage, totalPages - 1));
            updateProgress();
        }

        // Store scroll percentage for resize preservation
        if (content.scrollWidth > 0) {
            scrollPercentage = container.scrollLeft / content.scrollWidth;
        }
    }

    /**
     * Handle window resize with position preservation
     */
    function handleResize() {
        if (!isPaginationEnabled()) {
            // Mobile mode - hide pagination elements
            if (progressIndicator) progressIndicator.style.display = 'none';
            if (navZoneLeft) navZoneLeft.style.display = 'none';
            if (navZoneRight) navZoneRight.style.display = 'none';
            return;
        }

        // Show pagination elements
        if (progressIndicator) progressIndicator.style.display = '';
        if (navZoneLeft) navZoneLeft.style.display = '';
        if (navZoneRight) navZoneRight.style.display = '';

        // Debounce resize handler
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            // Recalculate column width based on new container size
            updateColumnWidth();
            // Recalculate pages
            calculatePages();

            // Restore approximate reading position
            if (scrollPercentage > 0 && content.scrollWidth > 0) {
                const newScrollLeft = scrollPercentage * content.scrollWidth;
                container.scrollTo({
                    left: newScrollLeft,
                    behavior: 'auto'
                });
            }

            // Recalculate current page after scroll
            currentPage = Math.round(container.scrollLeft / pageWidth);
            currentPage = Math.max(0, Math.min(currentPage, totalPages - 1));
            updateProgress();
        }, 100);
    }

    /**
     * Initialize pagination module
     */
    function initPagination() {
        if (isInitialized) return;

        // Get DOM elements
        container = document.getElementById('pagination-container');
        content = document.getElementById('book-content');
        progressIndicator = document.getElementById('reading-progress');
        navZoneLeft = document.getElementById('nav-zone-left');
        navZoneRight = document.getElementById('nav-zone-right');
        prevChapterLink = document.getElementById('prev-chapter-link');
        nextChapterLink = document.getElementById('next-chapter-link');

        if (!container || !content) {
            console.warn('Pagination: Required elements not found');
            return;
        }

        // Check if pagination should be enabled
        if (!isPaginationEnabled()) {
            if (progressIndicator) progressIndicator.style.display = 'none';
            if (navZoneLeft) navZoneLeft.style.display = 'none';
            if (navZoneRight) navZoneRight.style.display = 'none';
            return;
        }

        // Calculate initial pages
        // Wait for content to render, then ensure correct starting position
        setTimeout(() => {
            // Set column width dynamically based on actual container size
            updateColumnWidth();
            // Reset scroll to beginning of first page
            container.scrollLeft = 0;
            calculatePages();
            updateProgress();
        }, 50);

        // Set up event listeners
        document.addEventListener('keydown', handleKeydown);
        container.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('resize', handleResize);

        // Navigation zone click handlers (skip if text is selected)
        if (navZoneLeft) {
            navZoneLeft.addEventListener('click', (e) => {
                if (hasActiveSelection()) return; // Don't navigate during text selection
                e.preventDefault();
                prevPage();
            });
        }

        if (navZoneRight) {
            navZoneRight.addEventListener('click', (e) => {
                if (hasActiveSelection()) return; // Don't navigate during text selection
                e.preventDefault();
                nextPage();
            });
        }

        isInitialized = true;
        console.log('Pagination: Initialized');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPagination);
    } else {
        initPagination();
    }

    // Expose API for debugging
    window.Pagination = {
        nextPage,
        prevPage,
        navigateToPage,
        getCurrentPage: () => currentPage,
        getTotalPages: () => totalPages,
        recalculate: () => {
            updateColumnWidth();
            calculatePages();
            updateProgress();
        },
        updateColumnWidth
    };
})();
