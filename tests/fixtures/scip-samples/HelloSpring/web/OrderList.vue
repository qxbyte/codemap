<template>
  <div>Order List</div>
</template>

<script>
export default {
  name: 'OrderList',
  methods: {
    calcPrice() {
      return this.$axios.post('/api/order/price', { userId: 1 })
    },
  },
}
</script>
