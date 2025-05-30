# Card Animation Component Task Description

## Objective

Implement an interactive card slider component featuring two distinct animation modes: a linear horizontal movement for cards in the center view and a visually appealing "fanned" stacking animation for cards accumulating on the left and right sides of the view. Ensure a smooth, seamless transition between these two modes.

## Requirements

1.  **Component Structure:**
    *   Use HTML for the basic structure (container, track, individual cards, navigation arrows).
    *   Use CSS for styling (card dimensions, appearance, shadows, base transitions). Utilize CSS variables for key parameters.
    *   Use JavaScript to manage the component's state, handle user interactions (drag, click), and calculate card positions dynamically.

2.  **Center Animation:**
    *   Cards near the horizontal center of the container should move linearly left or right based on user interaction (dragging or clicking navigation arrows).
    *   Maintain appropriate spacing (`--card-gap`) between cards in the center view.

3.  **Stacking Animation:**
    *   Cards moving beyond a certain threshold on the left or right should transition into a "stack".
    *   **Fanning:** The top 5 cards (`--stack-limit`) in each stack should be visually offset *towards* the center of the screen. The offset should decreass progressively for deeper cards (e.g., 2% of card width per card - `--fan-offset-percent`). Cards beyond the 5th should align with the 5th card's offset.
    *   Stacks should form at defined base positions near the edges of the container (`--stack-base-percent`, `--stack-base-percent`).

4.  **Smooth Transition:**
    *   Implement a immediate switch as a card moves from the linear center track into the stack animation stack, and vice-versa.
    *   The top 5 cards (`--stack-limit`) shold start animating as the new top card is still `--fan-offset-percent` awai from switching to stack animation itself. In this way the stack is visually ready to accomodate the new card as it is switched into the stack animation track.

5.  **Interaction:**
    *   Support dragging the cards left/right to scroll through them.
    *   Provide clickable left/right navigation arrows.
    *   Ensure smooth snapping to the nearest logical card position upon ending a drag or clicking an arrow.

6.  **Z-Index Management:**
    *   Cards in the center should appear above transitioning cards and stacked cards.
    *   Transitioning cards should appear above stacked cards.
    *   Cards within a stack should layer correctly (topmost card highest z-index within the stack).

