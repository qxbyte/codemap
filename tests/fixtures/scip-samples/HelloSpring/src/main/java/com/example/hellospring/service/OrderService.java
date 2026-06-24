package com.example.hellospring.service;

import com.example.hellospring.mapper.CouponMapper;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.List;

@Service
public class OrderService {

    private final CouponMapper couponMapper;

    public OrderService(CouponMapper couponMapper) {
        this.couponMapper = couponMapper;
    }

    public BigDecimal calculateOrderPrice(long userId) {
        List<BigDecimal> coupons = couponMapper.selectByUser(userId);
        BigDecimal base = new BigDecimal("100.00");
        BigDecimal discount = BigDecimal.ZERO;
        for (BigDecimal c : coupons) {
            discount = discount.add(c);
        }
        return base.subtract(discount);
    }
}
