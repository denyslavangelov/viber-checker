"use client";

import { forwardRef, useImperativeHandle, useCallback } from "react";
import type { AnimatedIconHandle, AnimatedIconProps } from "./types";
import { useAnimate } from "motion/react";

const UserIcon = forwardRef<AnimatedIconHandle, AnimatedIconProps>(
  (
    {
      size = 24,
      color = "currentColor",
      strokeWidth = 2,
      className = "",
      ...rest
    },
    ref
  ) => {
    const [scope, animate] = useAnimate();

    const start = useCallback(async () => {
      await animate(
        ".user-avatar",
        { scale: 1.05, y: -1 },
        { duration: 0.25, ease: "easeOut" }
      );
    }, [animate]);

    const stop = useCallback(async () => {
      await animate(
        ".user-avatar",
        { scale: 1, y: 0 },
        { duration: 0.2, ease: "easeInOut" }
      );
    }, [animate]);

    useImperativeHandle(ref, () => ({
      startAnimation: start,
      stopAnimation: stop,
    }));

    const s = typeof size === "number" ? `${size}px` : size;
    return (
      <svg
        ref={scope}
        width={s}
        height={s}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        {...rest}
      >
        <g className="user-avatar">
          {/* Circle frame */}
          <circle cx="12" cy="12" r="9" />
          {/* Head */}
          <circle cx="12" cy="9.5" r="3" />
          {/* Shoulders / body */}
          <path d="M7 14.5c0-1.5 2.2-3 5-3s5 1.5 5 3" />
        </g>
      </svg>
    );
  }
);

UserIcon.displayName = "UserIcon";
export default UserIcon;
