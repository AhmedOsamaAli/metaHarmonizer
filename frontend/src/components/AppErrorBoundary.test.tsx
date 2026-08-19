import { isValidElement } from 'react';
import { describe, expect, it } from 'vitest';
import AppErrorBoundary from './AppErrorBoundary';

describe('AppErrorBoundary', () => {
  it('renders children before a failure', () => {
    const boundary = new AppErrorBoundary({ children: 'content' });
    expect(boundary.render()).toBe('content');
  });

  it('renders a recovery action after a failure', () => {
    const boundary = new AppErrorBoundary({ children: 'content' });
    boundary.state = AppErrorBoundary.getDerivedStateFromError();
    const fallback = boundary.render();
    expect(isValidElement(fallback)).toBe(true);
    expect(fallback).not.toBe('content');
  });
});