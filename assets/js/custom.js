// Landscape orientation warning for mobile devices
(function() {
    'use strict';

    function checkOrientation() {
        const modal = document.getElementById('kko-landscape-warning');
        if (!modal) return;

        // More reliable mobile detection using multiple methods
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
                        window.matchMedia('(max-width: 926px)').matches; // iPhone 12 Pro Max width

        // Check orientation using multiple methods for iOS compatibility
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;
        const isLandscape = windowWidth > windowHeight;

        // Alternative: use orientation API if available
        const orientationAngle = window.orientation !== undefined ? Math.abs(window.orientation) === 90 : false;
        const mediaLandscape = window.matchMedia('(orientation: landscape)').matches;

        // Combine checks for maximum compatibility
        const isActuallyLandscape = isLandscape || orientationAngle || mediaLandscape;

        if (isMobile && isActuallyLandscape && windowHeight < 500) {
            // Show modal using UIKit
            UIkit.modal(modal).show();
        } else {
            // Hide modal using UIKit
            UIkit.modal(modal).hide();
        }
    }

    // Check on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkOrientation);
    } else {
        checkOrientation();
    }

    // Check on orientation change
    window.addEventListener('orientationchange', function() {
        // Longer delay for iOS to ensure DOM has updated
        setTimeout(checkOrientation, 300);
    });

    // Also listen to resize events as backup
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(checkOrientation, 100);
    });

    // For iOS, also check on screen orientation change API if available
    if (screen.orientation) {
        screen.orientation.addEventListener('change', function() {
            setTimeout(checkOrientation, 300);
        });
    }
})();
