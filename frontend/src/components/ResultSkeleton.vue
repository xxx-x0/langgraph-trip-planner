<template>
  <div class="result-skeleton">
    <div class="skeleton-header">
      <div class="skeleton-avatar animate-shimmer"></div>
      <div class="skeleton-header-text">
        <div class="skeleton-line long animate-shimmer"></div>
        <div class="skeleton-line short animate-shimmer"></div>
      </div>
    </div>
    <div class="skeleton-days">
      <div v-for="i in 3" :key="i" class="skeleton-day">
        <div class="skeleton-day-header animate-shimmer"></div>
        <div class="skeleton-day-content">
          <div v-for="j in 3" :key="j" class="skeleton-card">
            <div class="skeleton-card-image animate-shimmer"></div>
            <div class="skeleton-card-body">
              <div class="skeleton-line long animate-shimmer"></div>
              <div class="skeleton-line medium animate-shimmer"></div>
              <div class="skeleton-line short animate-shimmer"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.result-skeleton {
  padding: var(--space-6);
  max-width: var(--content-max-width);
  margin: 0 auto;
}

.skeleton-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-8);
}

.skeleton-avatar {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-circle);
  flex-shrink: 0;
}

.skeleton-header-text {
  flex: 1;
}

.skeleton-line {
  height: 14px;
  border-radius: var(--radius-pill);
  margin-bottom: var(--space-2);
}

.skeleton-line.long {
  width: 60%;
}

.skeleton-line.medium {
  width: 40%;
}

.skeleton-line.short {
  width: 25%;
}

.skeleton-days {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.skeleton-day-header {
  height: 32px;
  width: 180px;
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-4);
}

.skeleton-day-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.skeleton-card {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border-light);
}

.skeleton-card-image {
  height: 180px;
}

.skeleton-card-body {
  padding: var(--space-4);
}

@media (max-width: 768px) {
  .result-skeleton {
    padding: var(--space-4);
  }

  .skeleton-day-content {
    grid-template-columns: 1fr;
  }
}
</style>
