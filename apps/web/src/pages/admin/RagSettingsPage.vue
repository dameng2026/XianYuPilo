<template>
  <div class="rag-settings-page">
    <section class="page-hero">
      <div class="page-hero-copy">
        <span class="page-pill">Knowledge Base Workspace</span>
        <h1>RAG 知识库</h1>
        <p>
          知识库管理已经从系统总览中拆分出来。现在可以在一个独立页面里完成知识库创建、
          文档上传、分块索引和检索测试，避免与其他系统配置相互打扰。
        </p>
      </div>

      <div class="hero-side">
        <div class="hero-note">
          <strong>独立工作区</strong>
          <span>适合持续维护 FAQ、售后说明、商品知识与行业文档。</span>
        </div>
      </div>
    </section>

    <RagKnowledgeBasePage />
  </div>
</template>

<script setup>
import RagKnowledgeBasePage from './RagKnowledgeBasePage.vue'

defineProps({ active: String })
</script>

<style scoped>
.rag-settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 16px;
  padding: 22px;
  border-radius: 24px;
  border: 1px solid rgba(231, 237, 247, 0.95);
  background:
    radial-gradient(circle at top left, rgba(99, 102, 241, 0.1), transparent 30%),
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 35%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.92));
  box-shadow: 0 18px 42px rgba(31, 53, 94, 0.08);
}

.page-pill {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.08);
  color: #5145cd;
  font-size: 11px;
  font-weight: 800;
}

.page-hero-copy h1 {
  margin: 10px 0 0;
  font-size: 28px;
  color: #13213d;
}

.page-hero-copy p {
  margin: 10px 0 0;
  max-width: 760px;
  line-height: 1.8;
  color: #60738e;
}

.hero-side {
  display: flex;
  align-items: stretch;
}

.hero-note {
  width: 100%;
  padding: 16px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(244, 239, 255, 0.98), rgba(255, 255, 255, 0.96));
  border: 1px solid rgba(231, 237, 247, 0.95);
}

.hero-note strong {
  display: block;
  color: #13213d;
  font-size: 18px;
}

.hero-note span {
  display: block;
  margin-top: 8px;
  color: #667892;
  line-height: 1.7;
}

@media (max-width: 1080px) {
  .page-hero {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .rag-settings-page {
    gap: 12px;
  }

  .page-hero {
    grid-template-columns: minmax(0, 1fr);
    padding: 14px;
    border-radius: 16px;
    gap: 12px;
  }

  .page-hero > * {
    min-width: 0;
  }

  .page-hero-copy h1 {
    font-size: 20px;
  }

  .page-hero-copy p {
    font-size: 13px;
    line-height: 1.6;
  }

  .hero-side {
    width: 100%;
  }

  .hero-note {
    padding: 12px;
    border-radius: 14px;
  }

  .hero-note strong {
    font-size: 15px;
  }

  .hero-note span {
    margin-top: 6px;
    font-size: 13px;
    line-height: 1.6;
  }
}
</style>
